from .common import *


class AiMixin:
    def _ai_model_key_for_wt(self, wt=None):
        """Return the dedicated AI model key: WT 12.70 or WT 10.31 mm."""
        if wt is None:
            wt = self.get_global_wall_thickness()
        try:
            wt = float(wt)
        except Exception:
            return None
        if not np.isfinite(wt):
            return None
        return 12.70 if abs(wt - 12.70) <= abs(wt - 10.31) else 10.31


    def _sync_active_ai_model(self):
        """Point legacy self.ai_model aliases at the model for current WT."""
        key = self._ai_model_key_for_wt()
        self.ai_model = self.ai_models.get(key) if key is not None else None
        self.ai_model_info = self.ai_model_infos.get(key, {}) if key is not None else {}
        return key, self.ai_model


    @staticmethod
    def _ai_numeric(value):
        """Convert Excel numeric values such as 29.1 or 'Ø29.1' to float."""
        if isinstance(value, (int, float, np.integer, np.floating)):
            try:
                v = float(value)
                return v if np.isfinite(v) else np.nan
            except Exception:
                return np.nan
        if value is None:
            return np.nan
        m = re.search(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', str(value).replace(',', ''))
        if not m:
            return np.nan
        try:
            return float(m.group(0))
        except Exception:
            return np.nan


    @staticmethod
    def _ai_extint_code(value):
        text = str(value or '').strip().lower()
        return 1.0 if text.startswith('int') or text in ('id', 'internal') else 0.0


    def browse_ai_training_file(self, wt_key):
        path = filedialog.askopenfilename(
            title=f'Select AI depth training workbook for WT {wt_key:.2f} mm',
            filetypes=[('Excel workbook', '*.xlsx'), ('Excel 97-2003', '*.xls'), ('All files', '*.*')]
        )
        if path:
            if abs(float(wt_key) - 12.70) < 0.01:
                self.ai_training_path_127_var.set(path)
            else:
                self.ai_training_path_1031_var.set(path)


    @staticmethod
    def _ai_physics_features(max_raw, ext_code, length, width, velocity, thickness):
        """Physics-model feature vector used for BOTH training and prediction.

        IMPORTANT:
        - ROI number is intentionally NOT used as an AI input.
        - Actual Depth is output only; it is never used during prediction.
        - Inputs are physical/measured values available for a new unknown defect:
          Max Raw, Ext/Int, Length Selected, Width Selected, Velocity and Thickness.

        Feature order must remain identical in training and prediction:
        [Max Raw, Ext/Int code, Length, Width, Velocity, Thickness]
        """
        return np.asarray([
            float(max_raw),
            float(ext_code),
            float(length),
            float(width),
            float(velocity),
            float(thickness),
        ], dtype=float)


    @staticmethod
    def _ai_engineered_features(roi_no, max_raw, ext_code, length, width, velocity, thickness):
        return MultiDefectCSCANApp._ai_physics_features(
            max_raw, ext_code, length, width, velocity, thickness
        )


    def _read_ai_training_data(self, path):
        """Read physical AI inputs from one Excel workbook.

        Required columns:
        Max Raw | Ext/Int | Length | Width | Depth | Velocity | Thickness

        Depth is the target/output. ROI, if present, is kept only as a label for
        diagnostics and is NEVER passed to the model.
        """
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(f'Training file not found: {path}')
        wb = load_workbook(path, data_only=True, read_only=True)
        ws = wb.active
        headers = [str(c.value or '').strip() for c in next(ws.iter_rows(min_row=1, max_row=1))]

        aliases = {
            'maxraw': ['maxraw'],
            'extint': ['ext/int', 'extint', 'idod'],
            'length': ['length'],
            'width': ['width'],
            'depth': ['depth'],
            'velocity': ['velocity', 'speed'],
            'thickness': ['thickness', 'wallthickness', 'wt'],
        }
        col = {}
        for key, names in aliases.items():
            found = None
            normalized_names = [n.lower().replace(' ', '').replace('_', '') for n in names]
            for original_i, h in enumerate(headers):
                hn = h.lower().replace(' ', '').replace('_', '')
                if hn in normalized_names:
                    found = original_i
                    break
            if found is None:
                raise ValueError(f'Missing required training column: {key}')
            col[key] = found

        roi_col = None
        roi_aliases = {'roi', 'roino', 'roi#', 'defect', 'defectno', 'defectnumber'}
        for original_i, h in enumerate(headers):
            hn = h.lower().replace(' ', '').replace('_', '')
            if hn in roi_aliases:
                roi_col = original_i
                break

        X, y, ext_labels, roi_labels = [], [], [], []
        valid_index = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            max_raw = self._ai_numeric(row[col['maxraw']])
            length = self._ai_numeric(row[col['length']])
            width = self._ai_numeric(row[col['width']])
            depth = self._ai_numeric(row[col['depth']])
            velocity = self._ai_numeric(row[col['velocity']])
            thickness = self._ai_numeric(row[col['thickness']])
            ext_raw = row[col['extint']]
            ext_code = self._ai_extint_code(ext_raw)

            if not all(np.isfinite(v) for v in (max_raw, length, width, depth, velocity, thickness)):
                continue

            roi_no = self._ai_numeric(row[roi_col]) if roi_col is not None else float(valid_index + 1)
            if not np.isfinite(roi_no):
                roi_no = float(valid_index + 1)

            X.append(self._ai_physics_features(
                max_raw, ext_code, length, width, velocity, thickness
            ))
            y.append(depth)
            ext_labels.append(str(ext_raw or '').strip())
            roi_labels.append(int(round(roi_no)))
            valid_index += 1

        wb.close()
        if len(X) < 8:
            raise ValueError(f'Only {len(X)} valid rows found. At least 8 are required.')
        return np.asarray(X, dtype=float), np.asarray(y, dtype=float), ext_labels, roi_labels, (roi_col is not None)


    def train_ai_depth_model(self):
        """Train ONE combined Physics AI model from the two imported WT files.

        The dedicated 12.70 workbook contributes only 12.70-mm rows and the
        dedicated 10.31 workbook contributes only 10.31-mm rows. This prevents
        duplicate 10.31-mm samples when a workbook contains mixed thicknesses.

        The final model is shared by both WT selections because Thickness itself
        is a physical input feature.
        """
        training_files = {
            12.70: self.ai_training_path_127_var.get().strip(),
            10.31: self.ai_training_path_1031_var.get().strip(),
        }
        try:
            X_parts, y_parts, ext_all = [], [], []
            rows_by_wt = {}

            for wt_key, path in training_files.items():
                if not path:
                    raise ValueError(f'Please import a training Excel file for WT {wt_key:.2f} mm.')

                X_file, y_file, ext_labels, _roi_labels, _has_roi = self._read_ai_training_data(path)

                # Thickness is feature index 5 in the Physics feature vector.
                # Keep only the intended wall-thickness family from each workbook.
                mask = np.isclose(X_file[:, 5], float(wt_key), atol=0.02)
                X_keep = X_file[mask]
                y_keep = y_file[mask]
                ext_keep = [e for e, keep in zip(ext_labels, mask) if keep]

                if len(y_keep) < 8:
                    raise ValueError(
                        f'WT {wt_key:.2f} mm: only {len(y_keep)} matching rows found in '
                        f'{os.path.basename(path)}.'
                    )

                X_parts.append(X_keep)
                y_parts.append(y_keep)
                ext_all.extend(ext_keep)
                rows_by_wt[wt_key] = int(len(y_keep))

            X = np.vstack(X_parts)
            y = np.concatenate(y_parts)

            # Same algorithm as the standalone Physics model previously tested.
            model = ExtraTreesRegressor(
                n_estimators=200,
                random_state=42,
                max_features=1.0,
                min_samples_leaf=1,
                n_jobs=-1,
            )

            # Honest small-dataset validation: each row is predicted by a model
            # that was trained without that row.
            loo = LeaveOneOut()
            pred_cv = cross_val_predict(model, X, y, cv=loo, n_jobs=1)
            mae = float(mean_absolute_error(y, pred_cv))
            rmse = float(np.sqrt(mean_squared_error(y, pred_cv)))
            r2 = float(r2_score(y, pred_cv))

            model.fit(X, y)
            pred_fit = model.predict(X)
            fit_mae = float(mean_absolute_error(y, pred_fit))
            fit_r2 = float(r2_score(y, pred_fit))

            unique_ext = sorted({str(v).strip() for v in ext_all if str(v).strip()})
            info = {
                'model': 'Physics ExtraTrees (ROI excluded)',
                'features': ['Max Raw', 'Ext/Int', 'Length', 'Width', 'Velocity', 'Thickness'],
                'training_files': dict(training_files),
                'n_rows': int(len(y)),
                'rows_by_wt': dict(rows_by_wt),
                'mae': mae,
                'rmse': rmse,
                'r2': r2,
                'fit_mae': fit_mae,
                'fit_r2': fit_r2,
                'ext_int_values': unique_ext,
                'uses_roi_number': False,
            }

            # Keep compatibility with the existing WT model selector. Both keys
            # point to the SAME combined physical model; Thickness differentiates WT.
            self.ai_models = {12.70: model, 10.31: model}
            self.ai_model_infos = {12.70: dict(info), 10.31: dict(info)}
            self._sync_active_ai_model()

            self.ai_status_var.set(
                f'Physics AI trained | N={len(y)} | '
                f'LOO R²={r2:.3f} | MAE={mae:.2f} mm | RMSE={rmse:.2f} mm | ROI excluded'
            )
            self.status_var.set(
                f'Physics AI ready: WT12.70={rows_by_wt[12.70]} rows + '
                f'WT10.31={rows_by_wt[10.31]} rows. '
                'Inputs = Max Raw, Ext/Int, Length, Width, Velocity, Thickness.'
            )
        except Exception as e:
            self.ai_models = {}
            self.ai_model_infos = {}
            self.ai_model = None
            self.ai_model_info = {}
            self.ai_status_var.set('Physics AI: training failed')
            messagebox.showerror('Train Physics AI', str(e))


    def _predict_ai_depth_for_roi(self, roi):
        """Predict Depth for ANY ROI from physical inputs only.

        No Actual Depth and no ROI number are required. Actual/reference values,
        when available for calibration ROI 1..26, are used only to calculate the
        displayed prediction error after prediction.
        """
        _model_key, model = self._sync_active_ai_model()
        if model is None:
            raise RuntimeError('Train the Physics AI model first.')

        self.calculate_peak_length(roi)
        max_raw = float(roi.get('max_raw_signal', roi.get('max_abs_signal', np.nan)))

        # Refresh optional actual/reference comparison, but NEVER require it.
        try:
            self._update_actual_comparison(roi)
        except Exception:
            pass

        length = float(roi.get('length_selected_mm', np.nan))
        width = float(roi.get('width_selected_mm', np.nan))
        velocity = float(self.ai_velocity_var.get())
        thickness = float(self.get_global_wall_thickness())
        ext_code = self._ai_extint_code(roi.get('ext_int', 'External'))

        vals = (max_raw, length, width, velocity, thickness)
        if not all(np.isfinite(v) for v in vals):
            raise ValueError(
                f"{roi.get('name','ROI')}: invalid Physics AI input(s). "
                f"Max Raw={max_raw}, Length={length}, Width={width}, "
                f"Velocity={velocity}, Thickness={thickness}"
            )

        feature_row = self._ai_physics_features(
            max_raw, ext_code, length, width, velocity, thickness
        ).reshape(1, -1)
        pred = float(model.predict(feature_row)[0])

        roi['ai_depth_mm'] = pred
        roi['ai_depth_pct'] = (100.0 * pred / thickness) if thickness > 0 else np.nan
        roi['depth'] = (
            f"{pred:.2f} mm / {roi['ai_depth_pct']:.1f}% (Physics AI)"
            if np.isfinite(roi.get('ai_depth_pct', np.nan))
            else f"{pred:.2f} mm (Physics AI)"
        )

        actual_depth = float(roi.get('actual_depth_mm', np.nan))
        if np.isfinite(actual_depth):
            roi['depth_error_mm'] = pred - actual_depth
            roi['depth_error_pct'] = (
                100.0 * roi['depth_error_mm'] / actual_depth if actual_depth else np.nan
            )
        else:
            roi['depth_error_mm'] = np.nan
            roi['depth_error_pct'] = np.nan

        roi['ai_features'] = {
            'model': 'Physics ExtraTrees',
            'max_raw': max_raw,
            'ext_int': roi.get('ext_int', 'External'),
            'length_mm': length,
            'width_mm': width,
            'length_selected_mm': length,
            'width_selected_mm': width,
            'velocity_mps': velocity,
            'thickness_mm': thickness,
            'length_source': roi.get('length_selected_method', ''),
            'width_source': roi.get('width_selected_method', ''),
            'actual_length_mm': roi.get('actual_length_mm', np.nan),
            'actual_width_mm': roi.get('actual_width_mm', np.nan),
            'actual_depth_mm': roi.get('actual_depth_mm', np.nan),
            'uses_roi_number': False,
        }
        return pred


    def predict_ai_depth_selected(self):
        roi = self.get_selected_roi()
        if roi is None:
            messagebox.showinfo('AI Depth', 'Select an ROI first.')
            return
        try:
            pred = self._predict_ai_depth_for_roi(roi)
            self.refresh_roi_tree_item(roi)

            # Keep the selected-ROI editor synchronized with the table.
            self.depth_var.set(str(roi.get('depth', '')))

            self.ai_status_var.set(
                f"{roi.get('name','ROI')}: L selected={roi.get('length_selected_mm', np.nan):.2f} mm | W selected={roi.get('width_selected_mm', np.nan):.2f} mm | AI Depth={pred:.2f} mm / {roi.get('ai_depth_pct', np.nan):.1f}% | V={float(self.ai_velocity_var.get()):.3g} m/s | WT={self.get_global_wall_thickness():.3g} mm"
            )
            self.status_var.set(f"{roi.get('name','ROI')}: AI Depth = {pred:.2f} mm")
        except Exception as e:
            messagebox.showerror('AI Depth', str(e))


    def predict_ai_depth_all(self):
        if not self.rois:
            messagebox.showinfo('AI Depth', 'Create at least one ROI first.')
            return
        ok, errors = 0, []
        for roi in self.rois:
            try:
                self._predict_ai_depth_for_roi(roi)
                self.refresh_roi_tree_item(roi)
                ok += 1
            except Exception as e:
                errors.append(str(e))
        # Rebuild the table once after the batch so all Depth / AI Depth cells
        # are guaranteed to reflect the latest predictions.
        if ok:
            self.renumber_rois()

        self.ai_status_var.set(f'AI predicted depth for {ok}/{len(self.rois)} ROI.')
        if errors:
            messagebox.showwarning('AI Depth', '\n'.join(errors[:10]))


