from .common import *


class ProjectIoMixin:
    def export_selected_csv(self):
        roi = self.get_selected_roi()
        if roi is None:
            messagebox.showinfo('Export', 'Select an ROI first.')
            return
        ds = next((d for d in self.datasets if d.path == roi['file_path']), None)

        # Clear only this ROI's previous analysis before recalculating it.
        # This prevents stale MAX/channel/length values from another calculation
        # from remaining visible when this box is recalculated.
        for key in (
            'max_abs_signal', 'max_raw_signal', 'max_abs_signed_value',
            'max_abs_x', 'max_raw_x', 'peak_channel',
            'peak_pos_x', 'peak_neg_x', 'peak_pos_value', 'peak_neg_value',
            'true_max_x', 'true_min_x', 'true_max_value', 'true_min_value',
            'length_mm', 'length_pp_mm', 'length_pp_base_mm',
            'threshold_length_mm', 'threshold_left_x', 'threshold_right_x',
            'threshold_level_signed'
        ):
            if key in ('peak_channel',):
                roi[key] = None
            else:
                roi[key] = np.nan

        if ds is None:
            return
        # Export from full signal; derivative is calculated BEFORE cropping.
        x, z_raw = ds.get(roi['axis'], roi['odo'], 'Raw')
        mask = (x >= roi['x1']) & (x <= roi['x2'])
        if not np.any(mask):
            messagebox.showerror('Export', 'No data points inside ROI.')
            return
        ch_indices = self._roi_channel_indices(roi, z_raw.shape[0])
        channel_numbers = (ch_indices + 1).astype(int).tolist()
        xcrop = x[mask]

        if roi['mode'] == 'Derivative' and x.size >= 3:
            with np.errstate(divide='ignore', invalid='ignore'):
                deriv_full = np.gradient(z_raw, x, axis=1)
            deriv_full[~np.isfinite(deriv_full)] = 0.0
            crop = deriv_full[ch_indices, :][:, mask]
        else:
            crop = z_raw[ch_indices, :][:, mask]

        threshold = abs(float(roi.get('threshold', 0.0)))
        if threshold > 0:
            crop = crop.copy()
            crop[np.abs(crop) < threshold] = 0.0

        default = f"{os.path.splitext(roi['file_name'])[0]}_{roi['name'].replace(' ', '_')}_{roi['axis']}_{roi['mode']}.csv"
        path = filedialog.asksaveasfilename(defaultextension='.csv', initialfile=default,
                                            filetypes=[('CSV files', '*.csv')])
        if not path:
            return
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Odometer_m'] + [f'Ch{c}' for c in channel_numbers])
            for j in range(xcrop.size):
                writer.writerow([xcrop[j]] + [crop[i, j] for i in range(crop.shape[0])])
        self.status_var.set(f'Exported {roi["name"]} to {path}')


    def _visible_table_columns(self):
        """Return currently visible Treeview data-column identifiers in display order."""
        if not hasattr(self, 'tree'):
            return []
        display = self.tree.cget('displaycolumns')
        if isinstance(display, str):
            display = self.root.tk.splitlist(display)
        display = list(display)
        if not display or display == ['#all']:
            return list(self.table_columns)
        return [c for c in display if c in self.table_columns]


    def _table_rows_as_tsv(self, only_selected=False):
        """Build a tab-separated copy of the currently visible ROI table."""
        cols = self._visible_table_columns()
        if not cols:
            return ''
        header = [self.table_column_labels.get(c, c) for c in cols]
        iids = list(self.tree.selection()) if only_selected else list(self.tree.get_children(''))
        if only_selected and not iids:
            iids = list(self.tree.get_children(''))
        lines = ['\t'.join(str(v) for v in header)]
        col_index = {c: i for i, c in enumerate(self.table_columns)}
        for iid in iids:
            values = list(self.tree.item(iid, 'values'))
            row = []
            for c in cols:
                idx = col_index[c]
                row.append(str(values[idx]) if idx < len(values) else '')
            lines.append('\t'.join(row))
        return '\n'.join(lines)


    def copy_table_to_clipboard(self):
        """Copy all currently visible ROI table columns/rows to the system clipboard."""
        text_data = self._table_rows_as_tsv(only_selected=False)
        if not text_data:
            messagebox.showinfo('Copy Table', 'There is no ROI table data to copy.')
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text_data)
        self.root.update_idletasks()
        self.status_var.set('Copied visible ROI table to clipboard (tab-separated; paste into Excel).')


    def copy_selected_table_rows(self, event=None):
        """Ctrl+C copies selected ROI rows; if none are selected, copy the whole table."""
        text_data = self._table_rows_as_tsv(only_selected=True)
        if text_data:
            self.root.clipboard_clear()
            self.root.clipboard_append(text_data)
            self.root.update_idletasks()
            self.status_var.set('Copied selected ROI row(s) to clipboard.')
        return 'break'


    @staticmethod
    def _json_safe(value):
        """Convert numpy/Tk-friendly values into plain JSON-safe Python values."""
        if isinstance(value, dict):
            return {str(k): MultiDefectCSCANApp._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [MultiDefectCSCANApp._json_safe(v) for v in value]
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float) and not np.isfinite(value):
            return None
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)


    def _project_state(self):
        """Capture settings, ROI records, view, table layout, and source-file mapping."""
        dataset_paths = [d.path for d in self.datasets]
        path_to_index = {p: i for i, p in enumerate(dataset_paths)}
        saved_rois = []
        for roi in self.rois:
            r = dict(roi)
            r['_dataset_index'] = path_to_index.get(roi.get('file_path'), -1)
            saved_rois.append(self._json_safe(r))

        try:
            xlim = [float(v) for v in self.ax.get_xlim()]
            ylim = [float(v) for v in self.ax.get_ylim()]
        except Exception:
            xlim = ylim = None
        try:
            page_y = list(self.left_scroll_canvas.yview())
        except Exception:
            page_y = [0.0, 1.0]

        current_index = -1
        if self.current is not None:
            for i, d in enumerate(self.datasets):
                if d.path == self.current.path:
                    current_index = i
                    break

        selected = self.tree.selection() if hasattr(self, 'tree') else ()
        return {
            'format': 'MFL_CSCAN_PROJECT',
            'version': 1,
            'datasets': [
                {'index': i, 'original_path': d.path, 'name': d.name}
                for i, d in enumerate(self.datasets)
            ],
            'current_dataset_index': current_index,
            'rois': saved_rois,
            'roi_counter': int(self.roi_counter),
            'selected_roi_id': int(selected[0]) if selected else None,
            'settings': {
                'axis': self.axis_var.get(),
                'mode': self.mode_var.get(),
                'odometer': int(self.odo_var.get()),
                'visible_channels': int(self.visible_channels_var.get()),
                'channel_start': int(self.channel_start_var.get()),
                'display_processing': self.display_processing_var.get(),
                'cscan_view': self.cscan_view_var.get(),
                'global_offset': self.global_offset_var.get(),
                'auto_sensor_offset': bool(self.auto_sensor_offset_var.get()),
                'color_min': self.vmin_var.get(),
                'color_max': self.vmax_var.get(),
                'color_yellow': self.vcenter_var.get(),
                'wall_thickness': self.wall_thickness_var.get(),
                'length_component': self.length_plot_component_var.get(),
                'width_component': self.width_plot_component_var.get(),
                'table_visible_columns': self._visible_table_columns(),
                'window_geometry': self.root.geometry(),
                'ai_training_path_127': self.ai_training_path_127_var.get(),
                'ai_training_path_1031': self.ai_training_path_1031_var.get(),
                'ai_velocity': self.ai_velocity_var.get(),
                'ai_model_info': self.ai_model_info,
                'ai_model_infos': {f'{float(k):.2f}': v for k, v in self.ai_model_infos.items()},
            },
            'view': {'xlim': xlim, 'ylim': ylim, 'page_y': page_y},
        }


    def save_project(self):
        """Save a self-contained .mflproj archive with CSV data and complete UI/ROI state."""
        if not self.datasets:
            messagebox.showinfo('Save Project', 'Open at least one CSV file before saving a project.')
            return
        path = filedialog.asksaveasfilename(
            title='Save MFL Project', defaultextension='.mflproj',
            filetypes=[('MFL Project', '*.mflproj'), ('All files', '*.*')]
        )
        if not path:
            return
        state = self._project_state()
        missing = []
        try:
            with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                for i, ds in enumerate(self.datasets):
                    src = ds.path
                    if not os.path.isfile(src):
                        missing.append(src)
                        continue
                    arc = f'data/{i:03d}_{os.path.basename(src)}'
                    zf.write(src, arcname=arc)
                    state['datasets'][i]['archive_name'] = arc
                # Save both wall-thickness-specific AI models.
                if self.ai_models:
                    state['ai_model_archives'] = {}
                    for wt_key, model in self.ai_models.items():
                        arc_model = f'ai/model_{float(wt_key):.2f}.pkl'
                        zf.writestr(arc_model, pickle.dumps(model, protocol=pickle.HIGHEST_PROTOCOL))
                        state['ai_model_archives'][f'{float(wt_key):.2f}'] = arc_model
                state['ai_training_archives'] = {}
                for wt_key, var in ((12.70, self.ai_training_path_127_var), (10.31, self.ai_training_path_1031_var)):
                    ai_training = var.get().strip()
                    if ai_training and os.path.isfile(ai_training):
                        arc_training = f'ai/training_{wt_key:.2f}.xlsx'
                        zf.write(ai_training, arcname=arc_training)
                        state['ai_training_archives'][f'{wt_key:.2f}'] = arc_training
                zf.writestr('project.json', json.dumps(state, ensure_ascii=False, indent=2))
            if missing:
                messagebox.showwarning('Save Project', 'Project saved, but some source files were missing:\n' + '\n'.join(missing))
            self.status_var.set(f'Saved project: {path}')
        except Exception as e:
            messagebox.showerror('Save Project', f'Could not save project:\n{e}')


    def load_project(self):
        """Load a .mflproj archive and restore data, ROIs, settings, table columns and view."""
        path = filedialog.askopenfilename(
            title='Load MFL Project', filetypes=[('MFL Project', '*.mflproj'), ('All files', '*.*')]
        )
        if not path:
            return
        try:
            temp_dir = tempfile.mkdtemp(prefix='mflproj_')
            with zipfile.ZipFile(path, 'r') as zf:
                state = json.loads(zf.read('project.json').decode('utf-8'))
                zf.extractall(temp_dir)
            self._project_temp_dirs.append(temp_dir)

            # Reset existing in-memory project without touching source files.
            self.disable_crop()
            self.datasets = []
            self.current = None
            self.rois = []
            self.roi_artists = []
            for item in self.tree.get_children(''):
                self.tree.delete(item)

            settings = state.get('settings', {})
            self.global_offset_var.set(str(settings.get('global_offset', '3')))
            offset = float(self.global_offset_var.get())
            self.auto_sensor_offset_var.set(bool(settings.get('auto_sensor_offset', False)))
            auto_sensor_offset = bool(self.auto_sensor_offset_var.get())

            errors = []
            for ds_info in state.get('datasets', []):
                arc = ds_info.get('archive_name')
                extracted = os.path.join(temp_dir, arc.replace('/', os.sep)) if arc else ''
                candidate = extracted if extracted and os.path.isfile(extracted) else ds_info.get('original_path', '')
                try:
                    ds = MFLData(candidate)
                    ds.offset = offset
                    ds.set_auto_sensor_offset(auto_sensor_offset)
                    self.datasets.append(ds)
                except Exception as e:
                    errors.append(f"{ds_info.get('name', candidate)}: {e}")
                    self.datasets.append(None)

            # Compact failed slots while keeping a mapping from saved index -> loaded dataset.
            old_to_new = {}
            good = []
            for old_i, ds in enumerate(self.datasets):
                if ds is not None:
                    old_to_new[old_i] = len(good)
                    good.append(ds)
            self.datasets = good
            if not self.datasets:
                raise RuntimeError('No dataset from this project could be loaded.')

            # Restore general settings before ROI recalculation/redraw.
            self.axis_var.set(settings.get('axis', 'X'))
            self.mode_var.set(settings.get('mode', 'Raw'))
            self.odo_var.set(int(settings.get('odometer', 1)))
            self.visible_channels_var.set(int(settings.get('visible_channels', 20)))
            self.channel_start_var.set(int(settings.get('channel_start', 1)))
            self.display_processing_var.set(settings.get('display_processing', 'Raw'))
            self.cscan_view_var.set(settings.get('cscan_view', 'Color C-scan'))
            self.vmin_var.set(settings.get('color_min', ''))
            self.vmax_var.set(settings.get('color_max', ''))
            self.vcenter_var.set(settings.get('color_yellow', ''))
            _loaded_wt = str(settings.get('wall_thickness', '12.7'))
            try:
                _loaded_wt_f = float(_loaded_wt)
            except Exception:
                _loaded_wt_f = 12.7
            _wt_choices = (12.70, 10.31)
            _loaded_wt_f = min(_wt_choices, key=lambda v: abs(_loaded_wt_f-v))
            self.wall_thickness_var.set('12.7' if _loaded_wt_f == 12.70 else f'{_loaded_wt_f:.2f}')
            self.length_plot_component_var.set(settings.get('length_component', 'Bx'))
            self.width_plot_component_var.set(settings.get('width_component', 'Bx'))
            self.ai_velocity_var.set(str(settings.get('ai_velocity', '0.7')))
            self.ai_model_info = settings.get('ai_model_info', {}) or {}
            raw_infos = settings.get('ai_model_infos', {}) or {}
            self.ai_model_infos = {}
            for k, v in raw_infos.items():
                try:
                    self.ai_model_infos[float(k)] = v
                except Exception:
                    pass
            training_archives = state.get('ai_training_archives', {}) or {}
            for wt_key, var, setting_key in (
                (12.70, self.ai_training_path_127_var, 'ai_training_path_127'),
                (10.31, self.ai_training_path_1031_var, 'ai_training_path_1031'),
            ):
                arc = training_archives.get(f'{wt_key:.2f}')
                extracted_ai = os.path.join(temp_dir, arc.replace('/', os.sep)) if arc else ''
                if extracted_ai and os.path.isfile(extracted_ai):
                    var.set(extracted_ai)
                else:
                    var.set(settings.get(setting_key, ''))

            self.ai_models = {}
            self.ai_model = None
            archives = state.get('ai_model_archives', {}) or {}
            for k, arc in archives.items():
                try:
                    wt_key = float(k)
                    model_path = os.path.join(temp_dir, arc.replace('/', os.sep))
                    if os.path.isfile(model_path):
                        with open(model_path, 'rb') as mf:
                            self.ai_models[wt_key] = pickle.load(mf)
                except Exception:
                    pass

            # Backward compatibility: old projects contain one ai/model.pkl only.
            if not self.ai_models:
                saved_model = state.get('ai_model_archive')
                if saved_model:
                    model_path = os.path.join(temp_dir, saved_model.replace('/', os.sep))
                    if os.path.isfile(model_path):
                        with open(model_path, 'rb') as mf:
                            legacy_model = pickle.load(mf)
                        key = self._ai_model_key_for_wt() or 12.70
                        self.ai_models[key] = legacy_model
                        if self.ai_model_info:
                            self.ai_model_infos[key] = self.ai_model_info

            active_key, active_model = self._sync_active_ai_model()
            if active_model is not None:
                info = self.ai_model_info
                self.ai_status_var.set(
                    f"AI model restored: WT {active_key:.2f} mm | {info.get('n_rows','?')} rows | "
                    f"MAE {info.get('mae',float('nan')):.2f} mm"
                    if info else f'AI model restored: WT {active_key:.2f} mm.'
                )
            elif self.ai_models:
                self.ai_status_var.set('AI models restored; no model matches the current WT selection.')
            geom = settings.get('window_geometry')
            if geom:
                try:
                    self.root.geometry(geom)
                except Exception:
                    pass

            visible_cols = settings.get('table_visible_columns', [])
            if visible_cols:
                for c, var in self.table_column_vars.items():
                    var.set(c in visible_cols)
                self.apply_table_column_visibility()

            self.file_combo['values'] = [d.name for d in self.datasets]
            saved_current = int(state.get('current_dataset_index', 0))
            current_new = old_to_new.get(saved_current, 0)
            self.file_combo.current(max(0, min(current_new, len(self.datasets) - 1)))
            self.current = self.datasets[self.file_combo.current()]
            if self.odo_var.get() not in self.current.odometers:
                self.odo_var.set(sorted(self.current.odometers)[0])

            restored_rois = []
            for raw_roi in state.get('rois', []):
                r = dict(raw_roi)
                old_idx = int(r.pop('_dataset_index', -1))
                if old_idx not in old_to_new:
                    continue
                ds = self.datasets[old_to_new[old_idx]]
                # JSON null was used for NaN/Inf; restore numeric missing values as NaN.
                for k, v in list(r.items()):
                    if v is None and (k.endswith('_mm') or k.endswith('_x') or k.endswith('_value') or k.startswith('true_') or k.startswith('peak_') or k.startswith('max_') or k.startswith('min_')):
                        r[k] = np.nan
                r['file_path'] = ds.path
                r['file_name'] = ds.name
                restored_rois.append(r)
            self.rois = restored_rois
            self.roi_counter = max(int(state.get('roi_counter', 0)), max([int(r.get('id', 0)) for r in self.rois], default=0))

            # Recalculate to ensure results match the restored global settings/data.
            for roi in self.rois:
                try:
                    self.calculate_peak_length(roi)
                    self.calculate_anomaly_dimension_class(roi)
                except Exception:
                    pass
            self.renumber_rois()
            self.redraw()

            # Restore exact C-scan view after the redraw.
            view = state.get('view', {})
            xlim, ylim = view.get('xlim'), view.get('ylim')
            if xlim and len(xlim) == 2:
                self.ax.set_xlim(float(xlim[0]), float(xlim[1]))
            if ylim and len(ylim) == 2:
                self.ax.set_ylim(float(ylim[0]), float(ylim[1]))
            self.canvas.draw_idle()
            self._update_cscan_scrollbars()

            selected_id = state.get('selected_roi_id')
            if selected_id is not None and self.tree.exists(str(selected_id)):
                self.tree.selection_set(str(selected_id))
                self.tree.focus(str(selected_id))
                self.tree.see(str(selected_id))
                self.on_roi_selected()

            page_y = view.get('page_y')
            if page_y:
                try:
                    self.root.after_idle(lambda: self.left_scroll_canvas.yview_moveto(float(page_y[0])))
                except Exception:
                    pass
            if errors:
                messagebox.showwarning('Load Project', 'Project loaded with some dataset errors:\n' + '\n'.join(errors))
            self.status_var.set(f'Loaded project: {path}')
        except Exception as e:
            messagebox.showerror('Load Project', f'Could not load project:\n{e}')


    def save_figure(self):
        if self.current is None:
            return
        path = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('PNG', '*.png'), ('PDF', '*.pdf')])
        if path:
            self.fig.savefig(path, dpi=200, bbox_inches='tight')
            self.status_var.set(f'Saved figure: {path}')


