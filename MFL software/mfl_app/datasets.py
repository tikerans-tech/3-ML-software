from .common import *
from .data import MFLData

class DatasetsMixin:
    def open_files(self):
        paths = filedialog.askopenfilenames(title='Select MFL CSV file(s)', filetypes=[('CSV files', '*.csv'), ('All files', '*.*')])
        if not paths:
            return
        loaded = 0
        errors = []
        for path in paths:
            try:
                ds = MFLData(path)
                # New datasets immediately inherit the current global offset.
                try:
                    ds.offset = float(self.global_offset_var.get())
                except Exception:
                    ds.offset = 3.0
                ds.set_auto_sensor_offset(bool(self.auto_sensor_offset_var.get()))
                self.datasets.append(ds)
                loaded += 1
            except Exception as e:
                errors.append(f'{os.path.basename(path)}: {e}')
        if loaded:
            self.file_combo['values'] = [d.name for d in self.datasets]
            self.file_combo.current(len(self.datasets) - loaded)
            self.change_dataset()
        if errors:
            messagebox.showwarning('Some files could not be opened', '\n'.join(errors))


    def apply_auto_sensor_offset(self):
        """Toggle automatic per-channel sensor offset correction for all data.

        When the checkbox changes, ALL ROI results are recalculated immediately:
        Raw maxima, Length/Width methods, selected Length/Width, table values and
        (when an AI model is already trained) AI Depth.  The current C-scan
        zoom/pan/channel-wrap position is preserved.
        """
        enabled = bool(self.auto_sensor_offset_var.get())

        # 1) Apply/disable calibration for every loaded dataset.
        for ds in self.datasets:
            ds.set_auto_sensor_offset(enabled)

        # Remember the selected ROI so its editor fields can be synchronized.
        selected_roi = self.get_selected_roi()

        recalculated = 0
        predicted = 0

        # 2) Recalculate every ROI using the newly calibrated/un-calibrated data.
        for roi in self.rois:
            try:
                self.calculate_peak_length(roi)
                self._update_actual_comparison(roi)

                # 3) If AI is already trained, refresh AI Depth automatically.
                # _predict_ai_depth_for_roi also refreshes the selected L/W
                # features before prediction, so the AI always uses the latest
                # sensor-offset-corrected Length Selected / Width Selected.
                if self.ai_model is not None:
                    try:
                        self._predict_ai_depth_for_roi(roi)
                        predicted += 1
                    except Exception:
                        # ROI >26 or incomplete AI features are intentionally
                        # skipped without breaking the sensor-offset toggle.
                        pass

                self.refresh_roi_tree_item(roi)
                recalculated += 1
            except Exception:
                pass

        # Keep the selected ROI editor synchronized with the recalculated result.
        if selected_roi is not None:
            try:
                self.depth_var.set(str(selected_roi.get('depth', '')))
                self.length_threshold_var.set(
                    f"{float(selected_roi.get('length_threshold', 50.0)):.6g}"
                )
                self.width_threshold_var.set(
                    f"{float(selected_roi.get('width_threshold', 50.0)):.6g}"
                )
            except Exception:
                pass

        # 4) Refresh visuals WITHOUT resetting the current view.
        self.redraw(preserve_view=True)
        try:
            self.update_selected_signal_plot()
        except Exception:
            pass

        state = 'ON' if enabled else 'OFF'
        ai_note = (
            f' AI Depth refreshed for {predicted} ROI.'
            if self.ai_model is not None
            else ' AI model is not trained, so Depth prediction was not changed.'
        )
        self.status_var.set(
            f'Auto Sensor Offset {state}: '
            f'{recalculated} ROI recalculated; per-channel baselines are '
            f'{"equalized" if enabled else "restored to original"}. '
            f'Global Offset remains separate.{ai_note}'
        )


    def apply_global_offset(self, event=None):
        """Apply one constant offset to Raw Bx/By/Bz for the entire program.

        The offset is added before all Raw-signal display and ROI calculations.
        A constant offset does not change spatial/channel derivatives, but it does
        shift Raw values such as Max Raw and the displayed Raw profiles.
        Existing zoom, circular channel position, and ROI boxes are preserved.
        """
        try:
            offset = float(self.global_offset_var.get().strip())
        except (ValueError, AttributeError):
            messagebox.showerror('Global Offset', 'Global Offset must be a numeric value.')
            self.global_offset_var.set('3')
            return 'break' if event is not None else None

        if not np.isfinite(offset):
            messagebox.showerror('Global Offset', 'Global Offset must be a finite numeric value.')
            self.global_offset_var.set('3')
            return 'break' if event is not None else None

        # Apply to every loaded dataset so every axis/component uses the same value.
        for ds in self.datasets:
            ds.offset = offset

        # Recalculate stored ROI results because Max Raw and all Raw-based values
        # should reflect the new offset immediately.
        for roi in self.rois:
            self.calculate_peak_length(roi)
            self.calculate_anomaly_dimension_class(roi)
            self.refresh_roi_tree_item(roi)

        # Refresh C-scan and selected plots without changing the user's view.
        if self.current is not None:
            self.redraw(preserve_view=True)
        selected = self.get_selected_roi()
        if selected is not None:
            try:
                self.draw_selected_signal_panel(selected)
            except Exception:
                pass

        self.status_var.set(
            f'Global Offset = {offset:g} applied to Raw Bx/By/Bz for all loaded data. '
            'Current zoom and ROI view preserved.'
        )
        return 'break' if event is not None and getattr(event, 'keysym', '') == 'Return' else None


    def change_dataset(self):
        idx = self.file_combo.current()
        if idx < 0 or idx >= len(self.datasets):
            return
        self.current = self.datasets[idx]
        # choose a valid odo if the requested one is absent
        if self.odo_var.get() not in self.current.odometers:
            self.odo_var.set(sorted(self.current.odometers)[0])
        self.redraw()


    def on_odometer_changed(self, event=None):
        """Use the selected odometer for C-scan and all Length calculations.

        Existing ROIs on the current dataset keep the same sample-index window,
        but their x1/x2 coordinates are remapped to the newly selected odometer.
        This means Width remains unchanged while Length P-P / Threshold sizing
        is recalculated from the newly selected Odo distance axis.
        """
        if self.current is None:
            return

        new_odo = int(self.odo_var.get())
        if new_odo not in self.current.odometers:
            messagebox.showerror('Odometer', f'Odometer {new_odo} is not available in this file.')
            return

        # Read the new odometer coordinate array once.  The magnetic samples are
        # the same sample indices; only their distance coordinate changes.
        x_new = np.asarray(self.current.odometers[new_odo], dtype=float)
        if x_new.size == 0:
            return

        # Keep the same orientation rule used by MFLData.get().
        reverse = x_new.size > 1 and np.nanmedian(np.diff(x_new)) < 0
        if reverse:
            x_new = x_new[::-1]

        updated = 0
        for roi in self.rois:
            if roi.get('file_path') != self.current.path:
                continue

            # Existing ROI stores exact sample indices from the crop.  Reuse
            # those indices so switching Odo does not move the ROI to another
            # defect; only the distance scale changes.
            try:
                i1 = int(roi.get('sample_i1'))
                i2 = int(roi.get('sample_i2'))
            except Exception:
                # Fallback: map current ROI limits to indices on the old Odo.
                old_odo = int(roi.get('odo', new_odo))
                try:
                    old_x, _ = self.current.get(roi.get('axis', self.axis_var.get()), old_odo, 'Raw')
                    i1 = int(np.nanargmin(np.abs(old_x - float(roi.get('x1', old_x[0])))))
                    i2 = int(np.nanargmin(np.abs(old_x - float(roi.get('x2', old_x[-1])))))
                except Exception:
                    continue

            if i2 < i1:
                i1, i2 = i2, i1
            i1 = max(0, min(i1, x_new.size - 1))
            i2 = max(0, min(i2, x_new.size - 1))

            roi['sample_i1'] = i1
            roi['sample_i2'] = i2
            roi['odo'] = new_odo
            roi['x1'] = float(x_new[i1])
            roi['x2'] = float(x_new[i2])

            try:
                self.calculate_peak_length(roi)
                # Recompute actual comparison / AI-selected dimensions if the
                # helper exists in this version.
                if hasattr(self, '_update_actual_comparison'):
                    self._update_actual_comparison(roi)
                updated += 1
            except Exception:
                pass

        # Rebuild the table so all Length values immediately reflect the new Odo.
        if self.rois:
            self.renumber_rois()

        # Dataset/Odo changed: redraw the C-scan using the selected Odo.
        self.redraw()

        # Refresh the selected ROI signal plots too.
        try:
            self.update_selected_signal_plot()
        except Exception:
            pass

        self.status_var.set(
            f'Odometer {new_odo} selected. Recalculated Length for {updated} ROI(s); Width is unchanged.'
        )


    def get_global_wall_thickness(self):
        """Return the single wall-thickness value used by every ROI."""
        text = self.wall_thickness_var.get().strip()
        if not text:
            return np.nan
        try:
            wt = float(text)
        except ValueError:
            return np.nan
        return wt if wt > 0 else np.nan


    def on_global_wt_changed(self, event=None):
        """Apply selected wall thickness and switch to its dedicated AI model."""
        text = self.wall_thickness_var.get().strip()
        try:
            wt = float(text)
        except ValueError:
            wt = 12.7
        choices = (12.70, 10.31)
        wt = min(choices, key=lambda v: abs(wt - v))
        self.wall_thickness_var.set('12.7' if wt == 12.70 else f'{wt:.2f}')

        model_key, active_model = self._sync_active_ai_model()

        for roi in self.rois:
            roi['wall_thickness_mm'] = wt
            self.calculate_anomaly_dimension_class(roi)
            self._update_actual_comparison(roi)
            self.refresh_roi_tree_item(roi)

        selected = self.get_selected_roi()
        if selected is not None:
            self.anomaly_class_var.set(str(selected.get('anomaly_class', 'Set WT')))

        self.status_var.set(
            f'Global WT = {wt:.2f} mm applied to all {len(self.rois)} ROI; '
            f'AI model = {model_key:.2f} mm family ({"ready" if active_model is not None else "not trained"}); '
            'Actual dimensions and Length/Width errors recalculated.'
        )
        return None


