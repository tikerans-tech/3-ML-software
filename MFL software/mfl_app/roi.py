from .common import *


class RoiMixin:
    def _roi_channel_indices(self, roi, n_channels):
        """Return ROI physical channel indices in circular crop order (0-based)."""
        vals = roi.get('channel_indices')
        if vals is not None:
            arr = np.asarray(vals, dtype=int).ravel()
            arr = arr[(arr >= 0) & (arr < n_channels)]
            if arr.size:
                return arr
        # Backward compatibility with ROI created by older versions.
        c1 = max(1, int(roi.get('ch1', 1)))
        c2 = min(n_channels, int(roi.get('ch2', n_channels)))
        if c2 < c1:
            c1, c2 = c2, c1
        return np.arange(c1 - 1, c2, dtype=int)


    def _roi_channel_label(self, roi):
        nums = roi.get('channel_numbers')
        if nums:
            nums = [int(v) for v in nums]
        else:
            nums = [int(v)+1 for v in self._roi_channel_indices(roi, int(getattr(self, '_n_channels', 0) or max(roi.get('ch2',1),1)))]
        if not nums:
            return '-'
        # Compact circular ranges, e.g. 68-70,1-4.
        groups=[]
        st=pr=nums[0]
        for v in nums[1:]:
            if v == pr + 1:
                pr=v
            else:
                groups.append((st,pr)); st=pr=v
        groups.append((st,pr))
        return ','.join(str(a) if a==b else f'{a}-{b}' for a,b in groups)


    def on_select_roi(self, eclick, erelease):
        if self.current is None or eclick.xdata is None or erelease.xdata is None or eclick.ydata is None or erelease.ydata is None:
            return
        x1_click, x2_click = sorted([float(eclick.xdata), float(erelease.xdata)])
        y1, y2 = sorted([float(eclick.ydata), float(erelease.ydata)])

        # Select the ACTUAL sample centers that are visually inside the dragged
        # rectangle.  The C-scan itself is plotted using matching cell edges, so
        # the samples searched below are exactly the cells seen inside the box.
        x_raw, z = self.current.get(self.axis_var.get(), self.odo_var.get(), 'Raw')
        x_edges = self._sample_edges(x_raw)

        inside_x = np.flatnonzero((x_raw >= x1_click) & (x_raw <= x2_click))
        if inside_x.size:
            i1, i2 = int(inside_x[0]), int(inside_x[-1])
        else:
            i1 = int(np.nanargmin(np.abs(x_raw - x1_click)))
            i2 = int(np.nanargmin(np.abs(x_raw - x2_click)))
            if i2 < i1:
                i1, i2 = i2, i1

        # Rectangle boundaries are the cell EDGES, while sample_i1/sample_i2
        # remain the exact numerical indices used for MAX/length calculations.
        x1 = float(x_edges[i1])
        x2 = float(x_edges[i2 + 1])

        # Y coordinates are DISPLAY rows, not physical channel numbers.
        # Map the selected rows through the current circular order.
        display_centers = np.arange(1, z.shape[0] + 1, dtype=float)
        inside_rows = np.flatnonzero((display_centers >= y1) & (display_centers <= y2))
        if inside_rows.size:
            r1, r2 = int(inside_rows[0]), int(inside_rows[-1])
        else:
            r1 = int(np.nanargmin(np.abs(display_centers - y1)))
            r2 = int(np.nanargmin(np.abs(display_centers - y2)))
            if r2 < r1:
                r1, r2 = r2, r1
        order = np.asarray(getattr(self, '_channel_display_order_cache', []), dtype=int)
        if order.size != z.shape[0]:
            order = self._channel_display_order(z.shape[0])
        channel_indices = np.asarray(order[r1:r2 + 1], dtype=int)
        channel_numbers = (channel_indices + 1).astype(int).tolist()
        ch1 = int(channel_numbers[0])
        ch2 = int(channel_numbers[-1])
        y1_snap = r1 + 0.5
        y2_snap = r2 + 1.5

        # Ask where this new ROI should be inserted in the display/calibration order.
        # Example: if ROI 1..10 already exist and the user chooses 4, the new ROI
        # becomes ROI 4 and the old ROI 4..10 shift to ROI 5..11.
        insert_no = simpledialog.askinteger(
            'ROI Number / Order',
            f'Insert this defect as which ROI number?\n\nValid range: 1 - {len(self.rois) + 1}',
            parent=self.root,
            initialvalue=len(self.rois) + 1,
            minvalue=1,
            maxvalue=len(self.rois) + 1,
        )
        if insert_no is None:
            # Cancel means cancel creation of this ROI; RectangleSelector stays active.
            self.status_var.set('ROI creation cancelled.')
            return

        self.roi_counter += 1
        roi = {
            'id': self.roi_counter,
            'name': '',
            'file_path': self.current.path,
            'file_name': self.current.name,
            'axis': self.axis_var.get(),
            'mode': self.mode_var.get(),
            'odo': self.odo_var.get(),
            'x1': x1,
            'x2': x2,
            'sample_i1': i1,
            'sample_i2': i2,
            'y1': y1_snap,
            'y2': y2_snap,
            'ch1': ch1,
            'ch2': ch2,
            'channel_indices': channel_indices.tolist(),
            'channel_numbers': channel_numbers,
            'display_row1': r1 + 1,
            'display_row2': r2 + 1,
            'channel_start_at_crop': self._get_channel_start(),
            # ROI width is only the search window. Defect length is detected
            # from derivative positive/negative peaks inside this ROI.
            'crop_length_mm': abs(float(x_raw[i2]) - float(x_raw[i1])) * 1000.0,
            'length_mm': np.nan,
            'length_pp_mm': np.nan,
            'fwhm_mm': np.nan,
            'length_fwhm_mm': np.nan,
            'threshold_length_mm': np.nan,
            'fwhm_left_x': np.nan,
            'fwhm_right_x': np.nan,
            'fwhm_half_level': np.nan,
            'fwhm_peak_sign': '',
            'peak_pos_x': np.nan,
            'peak_neg_x': np.nan,
            'peak_channel': None,
            'length_threshold': 50.0,
            'width_threshold': 50.0,
            'threshold': 50.0,  # legacy alias for length threshold
            # Width is calculated from RAW signal across channels at the x-position
            # of the true RAW maximum.  The same threshold percentage is used for
            # Length and Width.  Channel pitch is 6 mm.
            'requested_defect_count': 1,
            'channel_pitch_mm': 6.0,
            'width_crop_mm': max(0.0, (len(channel_indices) - 1) * 6.0),
            'width_pp_mm': np.nan,
            'width_pp_base_mm': np.nan,
            'threshold_width_mm': np.nan,
            'width_mm': np.nan,
            'width_peak_channel': None,
            'width_peak_x': np.nan,
            'depth': '',
            'ai_depth_mm': np.nan,
            'wall_thickness_mm': self.get_global_wall_thickness(),
            'anomaly_class': 'Set WT',
            'A_mm': np.nan,
            'ext_int': 'External',
        }
        # Insert at the requested display position instead of always appending.
        self.rois.insert(int(insert_no) - 1, roi)

        # Auto-calculate defect length from derivative peaks immediately.
        self.calculate_peak_length(roi)
        self.calculate_anomaly_dimension_class(roi)

        self.renumber_rois()

        # IMPORTANT: do NOT redraw the entire C-scan after cropping.
        # A full redraw clears/rebuilds pcolormesh, colorbar, ticks and overlays,
        # which looks like a refresh/flicker even when xlim/ylim are restored.
        # Instead, draw only the newly-created ROI overlay on the existing axes.
        self._draw_single_roi_overlay(roi)
        self._draw_single_roi_peak_markers(roi)
        self.canvas.draw_idle()

        # RectangleSelector remains usable after a completed selection, so there
        # is no need to destroy/re-create it here.  Re-enable only if it somehow
        # became inactive.
        if self.selector is None:
            self.enable_crop()
        if np.isfinite(roi.get('length_mm', np.nan)):
            self.status_var.set(
                f"Added {roi['name']}: derivative peak length = {roi['length_mm']:.2f} mm | "
                f"Ch {roi.get('peak_channel', '-')} | "
                f"MAX {roi.get('true_max_value', np.nan):.4g} | "
                f"MIN {roi.get('true_min_value', np.nan):.4g} | "
                f"Bx Raw Max @ Odo {roi.get('max_raw_x', np.nan):.6f} m | "
                f"Threshold Length {roi.get('threshold_length_mm', np.nan):.2f} mm | "
                f"Width P-P {roi.get('width_pp_mm', np.nan):.2f} mm | "
                f"Width @ Threshold {roi.get('threshold_width_mm', np.nan):.2f} mm. "
                f"Switch Signal to Derivative to see the peak markers on the same C-scan data."
            )
        else:
            self.status_var.set(
                f"Added {roi['name']}: no valid positive/negative derivative peak found."
            )


    @staticmethod
    def _fmt_mm(value):
        try:
            value = float(value)
            return f'{value:.2f}' if np.isfinite(value) else 'N/A'
        except Exception:
            return 'N/A'


    def _eight_dimension_values(self, roi):
        """Return the 8 requested sizing values in fixed table order."""
        LA = roi.get('length_analysis', {}) or {}
        WA = roi.get('width_analysis', {}) or {}
        bx_l = LA.get('X', {}) or {}
        bz_l = LA.get('Z', {}) or {}
        bx_w = WA.get('X', {}) or {}
        by_w = WA.get('Y', {}) or {}
        return (
            self._fmt_mm(bx_l.get('pp_x2_mm', np.nan)),
            self._fmt_mm(bx_l.get('mountain_mm', np.nan)),
            self._fmt_mm(bx_l.get('threshold_mm', np.nan)),
            self._fmt_mm(bz_l.get('pp_x2_mm', np.nan)),
            self._fmt_mm(bz_l.get('mountain_mm', np.nan)),
            self._fmt_mm(bz_l.get('threshold_mm', np.nan)),
            self._fmt_mm(bx_w.get('pp_x2_mm', np.nan)),
            self._fmt_mm(bx_w.get('mountain_mm', np.nan)),
            self._fmt_mm(bx_w.get('threshold_mm', np.nan)),
            self._fmt_mm(by_w.get('pp_x2_mm', np.nan)),
            self._fmt_mm(by_w.get('mountain_mm', np.nan)),
            self._fmt_mm(by_w.get('threshold_mm', np.nan)),
        )


    def _ai_roi_dimension_value(self, roi, source):
        """Return the numeric Length/Width value selected for AI/comparison."""
        LA = roi.get('length_analysis', {}) or {}
        WA = roi.get('width_analysis', {}) or {}
        mapping = {
            'Bx Length P-P': (LA.get('X', {}) or {}).get('pp_x2_mm', np.nan),
            'Bx Length Mountain': (LA.get('X', {}) or {}).get('mountain_mm', np.nan),
            'Bx Length @ Thr': (LA.get('X', {}) or {}).get('threshold_mm', np.nan),
            'Bz Length P-P': (LA.get('Z', {}) or {}).get('pp_x2_mm', np.nan),
            'Bz Length Mountain': (LA.get('Z', {}) or {}).get('mountain_mm', np.nan),
            'Bz Length @ Thr': (LA.get('Z', {}) or {}).get('threshold_mm', np.nan),
            'Bx Width P-P': (WA.get('X', {}) or {}).get('pp_x2_mm', np.nan),
            'Bx Width Mountain': (WA.get('X', {}) or {}).get('mountain_mm', np.nan),
            'Bx Width @ Thr': (WA.get('X', {}) or {}).get('threshold_mm', np.nan),
            'By Width P-P': (WA.get('Y', {}) or {}).get('pp_x2_mm', np.nan),
            'By Width Mountain': (WA.get('Y', {}) or {}).get('mountain_mm', np.nan),
            'By Width @ Thr': (WA.get('Y', {}) or {}).get('threshold_mm', np.nan),
        }
        try:
            return float(mapping.get(source, np.nan))
        except Exception:
            return np.nan


    def _actual_reference_for_roi(self, roi):
        """Return actual L/W/D/WT for ROI 1..26 using the selected WT set."""
        try:
            no = int(roi.get('display_no', 0))
        except Exception:
            no = 0
        if no < 1 or no > 26:
            return None
        wt = self.get_global_wall_thickness()
        if not np.isfinite(wt):
            return None
        ref_wt = 12.70 if abs(float(wt) - 12.70) < abs(float(wt) - 10.31) else 10.31
        L, W, D = self.actual_reference_sets[ref_wt][no - 1]
        return {'length_mm': float(L), 'width_mm': float(W), 'depth_mm': float(D), 'thickness_mm': float(ref_wt)}


    def _update_actual_comparison(self, roi):
        """Attach actual dimensions and apply the user-selected Length/Width methods."""
        ref = self._actual_reference_for_roi(roi)
        if ref is None:
            for key in ('actual_length_mm','actual_width_mm','actual_depth_mm','actual_depth_pct',
                        'actual_thickness_mm','best_length_mm','best_width_mm','best_length_error_mm',
                        'best_length_error_pct','best_width_error_mm','best_width_error_pct',
                        'length_error_mm','length_error_pct','width_error_mm','width_error_pct'):
                roi[key] = np.nan
            return None

        roi['actual_length_mm'] = ref['length_mm']
        roi['actual_width_mm'] = ref['width_mm']
        roi['actual_depth_mm'] = ref['depth_mm']
        roi['actual_thickness_mm'] = ref['thickness_mm']
        roi['actual_depth_pct'] = 100.0 * ref['depth_mm'] / ref['thickness_mm'] if ref['thickness_mm'] > 0 else np.nan

        length_sources = ['Bx Length P-P','Bx Length Mountain','Bx Length @ Thr','Bz Length P-P','Bz Length Mountain','Bz Length @ Thr']
        width_sources = ['Bx Width P-P','Bx Width Mountain','Bx Width @ Thr','By Width P-P','By Width Mountain','By Width @ Thr']

        # Preserve the user's per-ROI choice. Older projects fall back to the previous
        # selected source if available, otherwise Bx P-P.
        lsrc = roi.get('length_selected_method') or roi.get('best_length_source') or 'Bx Length P-P'
        wsrc = roi.get('width_selected_method') or roi.get('best_width_source') or 'Bx Width P-P'
        if lsrc not in length_sources:
            lsrc = 'Bx Length P-P'
        if wsrc not in width_sources:
            wsrc = 'Bx Width P-P'
        lval = self._ai_roi_dimension_value(roi, lsrc)
        wval = self._ai_roi_dimension_value(roi, wsrc)

        roi['best_length_source'] = lsrc
        roi['length_selected_method'] = lsrc
        roi['best_length_mm'] = float(lval) if np.isfinite(lval) else np.nan
        roi['length_selected_mm'] = roi['best_length_mm']
        if np.isfinite(lval):
            roi['best_length_error_mm'] = float(lval - ref['length_mm'])
            roi['length_error_mm'] = roi['best_length_error_mm']
            roi['best_length_error_pct'] = 100.0 * roi['best_length_error_mm'] / ref['length_mm'] if ref['length_mm'] else np.nan
            roi['length_error_pct'] = roi['best_length_error_pct']
        else:
            roi['best_length_error_mm'] = roi['length_error_mm'] = np.nan
            roi['best_length_error_pct'] = roi['length_error_pct'] = np.nan

        roi['best_width_source'] = wsrc
        roi['width_selected_method'] = wsrc
        roi['best_width_mm'] = float(wval) if np.isfinite(wval) else np.nan
        roi['width_selected_mm'] = roi['best_width_mm']
        if np.isfinite(wval):
            roi['best_width_error_mm'] = float(wval - ref['width_mm'])
            roi['width_error_mm'] = roi['best_width_error_mm']
            roi['best_width_error_pct'] = 100.0 * roi['best_width_error_mm'] / ref['width_mm'] if ref['width_mm'] else np.nan
            roi['width_error_pct'] = roi['best_width_error_error_pct'] if False else roi['best_width_error_pct']
        else:
            roi['best_width_error_mm'] = roi['width_error_mm'] = np.nan
            roi['best_width_error_pct'] = roi['width_error_pct'] = np.nan
        return ref


    def _format_error(self, error_mm, actual_mm):
        """Format signed error in mm and percent of the actual dimension."""
        try:
            e = float(error_mm)
            a = float(actual_mm)
            if not np.isfinite(e):
                return 'N/A'
            if np.isfinite(a) and a != 0:
                return f"{e:+.2f} mm ({100.0*e/a:+.1f}%)"
            return f"{e:+.2f} mm"
        except Exception:
            return 'N/A'


    def _actual_table_values(self, roi):
        self._update_actual_comparison(roi)
        def f(v, suffix=''):
            try:
                return f"{float(v):.2f}{suffix}" if np.isfinite(float(v)) else 'N/A'
            except Exception:
                return 'N/A'

        # Selected values. If the operator declared multiple defects inside one ROI,
        # show ALL calculated Length values in the Length selected cell, e.g.
        # "10.00, 7.00, 12.00 mm" instead of collapsing the ROI to one number.
        bl = f(roi.get('best_length_mm', np.nan))
        bw = f(roi.get('best_width_mm', np.nan))

        multi = list(roi.get('multi_defects', []) or [])
        requested_n = int(roi.get('requested_defect_count', 1) or 1)
        length_source = str(roi.get('best_length_source') or roi.get('length_selected_method') or '')
        if requested_n > 1 and len(multi) > 1:
            if 'P-P' in length_source:
                vals = [d.get('deriv_pp_mm', np.nan) for d in multi]
            else:
                # Multi-defect RAW sizing is calculated independently for every peak.
                # Use these values for @Threshold (and as a safe fallback for methods
                # that do not yet have a per-defect Mountain calculation).
                vals = [d.get('threshold_mm', np.nan) for d in multi]
            good = [float(v) for v in vals if np.isfinite(v)]
            if good:
                bl = ', '.join(f"{v:.2f}" for v in good) + ' mm'
                if length_source:
                    bl += f" ({length_source})"
        elif bl != 'N/A' and roi.get('best_length_source'):
            bl += f" ({roi['best_length_source']})"

        if bw != 'N/A' and roi.get('best_width_source'):
            bw += f" ({roi['best_width_source']})"

        length_err = self._format_error(
            roi.get('best_length_error_mm', np.nan), roi.get('actual_length_mm', np.nan)
        )
        width_err = self._format_error(
            roi.get('best_width_error_mm', np.nan), roi.get('actual_width_mm', np.nan)
        )

        try:
            ai = float(roi.get('ai_depth_mm', np.nan))
            actual_d = float(roi.get('actual_depth_mm', np.nan))
            depth_err = self._format_error(ai - actual_d, actual_d) if np.isfinite(ai) and np.isfinite(actual_d) else 'N/A'
        except Exception:
            depth_err = 'N/A'

        return {
            'actual_length': f(roi.get('actual_length_mm', np.nan)),
            'actual_width': f(roi.get('actual_width_mm', np.nan)),
            'actual_depth': f(roi.get('actual_depth_mm', np.nan)),
            'actual_depth_pct': f(roi.get('actual_depth_pct', np.nan), '%'),
            'actual_thickness': f(roi.get('actual_thickness_mm', np.nan)),
            'best_length': bl,
            'best_width': bw,
            'length_error': length_err,
            'width_error': width_err,
            'depth_error': depth_err,
        }


    def _format_ai_depth(self, roi):
        try:
            d = float(roi.get('ai_depth_mm', np.nan))
            wt = float(self.get_global_wall_thickness())
            if np.isfinite(d) and np.isfinite(wt) and wt > 0:
                return f"{d:.2f} mm / {100.0*d/wt:.1f}%"
            if np.isfinite(d):
                return f"{d:.2f} mm"
        except Exception:
            pass
        return 'N/A'


    def _distance_from_defect1_mm(self, roi):
        """Return absolute Bx-Max-Odo spacing from display Defect/ROI 1 in mm.

        Defect 1 is always the zero reference. Distances are only compared when
        both ROIs belong to the same source file and use the same odometer.
        """
        ref = next((r for r in self.rois if int(r.get('display_no', 0) or 0) == 1), None)
        if ref is None:
            return np.nan

        # Distance is physically meaningful only on the same scan / odometer axis.
        if roi.get('file_path') != ref.get('file_path') or roi.get('odo') != ref.get('odo'):
            return np.nan

        try:
            x_ref = float(ref.get('max_raw_x', np.nan))
            x_roi = float(roi.get('max_raw_x', np.nan))
        except Exception:
            return np.nan
        if not (np.isfinite(x_ref) and np.isfinite(x_roi)):
            return np.nan

        return abs(x_roi - x_ref) * 1000.0


    def _roi_table_row_values(self, roi):
        """Build one Treeview row in exactly self.table_columns order."""
        eight = self._eight_dimension_values(roi)
        actual = self._actual_table_values(roi)
        values = {
            'name': roi.get('name', ''),
            'absmax': (f"{float(roi.get('max_abs_signal', np.nan)):.4g}"
                       if np.isfinite(roi.get('max_abs_signal', np.nan)) else 'N/A'),
            # Odometer coordinate of the highest signed Bx Raw sample inside this ROI.
            'bx_max_odo': (f"{float(roi.get('max_raw_x', np.nan)):.6f}"
                           if np.isfinite(roi.get('max_raw_x', np.nan)) else 'N/A'),
            # Defect 1 is the zero reference; all other defects show absolute spacing
            # between their Bx Raw maximum Odo and Defect 1, converted m -> mm.
            'distance_from_defect1': (
                f"{self._distance_from_defect1_mm(roi):.1f}"
                if np.isfinite(self._distance_from_defect1_mm(roi)) else 'N/A'
            ),
            'bx_len_pp': eight[0], 'bx_len_mountain': eight[1], 'bx_len_thr': eight[2],
            'bz_len_pp': eight[3], 'bz_len_mountain': eight[4], 'bz_len_thr': eight[5],
            'bx_wid_pp': eight[6], 'bx_wid_mountain': eight[7], 'bx_wid_thr': eight[8],
            'by_wid_pp': eight[9], 'by_wid_mountain': eight[10], 'by_wid_thr': eight[11],
            **actual,
            'depth': str(roi.get('depth', '')),
            'velocity': (f"{float(self.ai_velocity_var.get()):.2f}"
                         if self._safe_float(self.ai_velocity_var.get()) == self._safe_float(self.ai_velocity_var.get()) else 'N/A'),
            'thickness': (f"{float(self.get_global_wall_thickness()):.2f}"
                          if self._safe_float(self.get_global_wall_thickness()) == self._safe_float(self.get_global_wall_thickness()) else 'N/A'),
            'ai_depth': self._format_ai_depth(roi),
            'anomaly_class': str(roi.get('anomaly_class', 'Set WT')),
            'ext_int': str(roi.get('ext_int', 'External')),
            'length_threshold': f"{float(roi.get('length_threshold', roi.get('threshold', 50.0))):.1f}%",
            'width_threshold': f"{float(roi.get('width_threshold', 50.0)):.1f}%",
        }
        return tuple(values.get(col, '') for col in self.table_columns)


    def renumber_rois(self, refresh_ai=True):
        """Renumber ROI names 1..N in current list order, preserving internal IDs.

        ROI number is also a calibration/AI feature in this version, so whenever
        the order changes we refresh Actual reference values and (if trained)
        AI Depth using the NEW ROI number.
        """
        for idx, roi in enumerate(self.rois, start=1):
            roi['display_no'] = idx
            roi['name'] = f'ROI {idx}'

        # Refresh any values that depend on ROI number.
        for roi in self.rois:
            try:
                self._update_actual_comparison(roi)
            except Exception:
                pass
            if refresh_ai and self.ai_model is not None:
                try:
                    self._predict_ai_depth_for_roi(roi)
                except Exception:
                    pass

        # Rebuild the tree in display order.
        selected = self.tree.selection()
        selected_id = selected[0] if selected else None

        for item in self.tree.get_children():
            self.tree.delete(item)

        for roi in self.rois:
            self.tree.insert(
                '', tk.END, iid=str(roi['id']),
                values=self._roi_table_row_values(roi)
            )

        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
            self.tree.focus(selected_id)
            self.tree.see(selected_id)
        self._schedule_class_cell_overlays()


    def change_selected_roi_number(self):
        """Move the selected ROI to a new display/calibration number.

        Moving ROI 8 to ROI 3, for example, inserts it at position 3 and shifts
        the previous ROI 3..7 down by one.  Internal IDs stay unchanged.
        """
        roi = self.get_selected_roi()
        if roi is None:
            messagebox.showinfo('ROI Number / Order', 'Please select an ROI first.')
            return
        if not self.rois:
            return

        old_no = int(roi.get('display_no', self.rois.index(roi) + 1))
        new_no = simpledialog.askinteger(
            'Change ROI Number / Order',
            f"Move {roi.get('name', f'ROI {old_no}')} to which ROI number?\n\n"
            f'Valid range: 1 - {len(self.rois)}',
            parent=self.root,
            initialvalue=old_no,
            minvalue=1,
            maxvalue=len(self.rois),
        )
        if new_no is None or int(new_no) == old_no:
            return

        selected_id = str(roi['id'])
        self.rois.remove(roi)
        self.rois.insert(int(new_no) - 1, roi)
        self.renumber_rois(refresh_ai=True)

        if self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
            self.tree.focus(selected_id)
            self.tree.see(selected_id)

        # Redraw ROI labels because the names/numbers shown on the C-scan changed.
        self.redraw(preserve_view=True)
        try:
            self.update_selected_signal_plot(roi)
        except Exception:
            pass
        self.status_var.set(
            f'Moved ROI {old_no} to ROI {int(new_no)}. Remaining ROI were shifted automatically; '
            'Actual reference and AI Depth were refreshed using the new order.'
        )


    def get_selected_roi(self):
        sel = self.tree.selection()
        if not sel:
            return None
        rid = int(sel[0])
        return next((r for r in self.rois if r['id'] == rid), None)


    @staticmethod
    def _interpolated_crossing(x1, y1, x2, y2, level):
        """Linear interpolation of x where a segment crosses a target level."""
        if not (np.isfinite(x1) and np.isfinite(x2) and np.isfinite(y1) and np.isfinite(y2)):
            return np.nan
        if y2 == y1:
            return float((x1 + x2) / 2.0)
        frac = (level - y1) / (y2 - y1)
        frac = min(1.0, max(0.0, float(frac)))
        return float(x1 + frac * (x2 - x1))


    @staticmethod
    def _calculate_mountain_width(x, y, peak_idx, unit_scale=1000.0):
        """Measure the full mountain base from nearest local valley left/right of the peak.

        No percentage threshold is used.  Starting at the selected positive peak,
        walk outward and choose the nearest local minimum on each side.
        If a clean local minimum is unavailable, fall back to the minimum on that side.
        Returns (width, left_x, right_x, left_idx, right_idx).
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if x.size != y.size or y.size < 3 or not np.any(np.isfinite(y)):
            return np.nan, np.nan, np.nan, None, None
        peak_idx = int(max(0, min(int(peak_idx), y.size - 1)))
        if peak_idx <= 0 or peak_idx >= y.size - 1:
            return np.nan, np.nan, np.nan, None, None
        yy = y.copy()
        # Light 3-point smoothing is used only to locate valleys; reported positions
        # remain on the original x samples.
        if yy.size >= 5:
            ys = np.convolve(yy, np.ones(3) / 3.0, mode='same')
            ys[0], ys[-1] = yy[0], yy[-1]
        else:
            ys = yy
        left_idx = None
        for i in range(peak_idx - 1, 0, -1):
            if np.isfinite(ys[i-1:i+2]).all() and ys[i] <= ys[i-1] and ys[i] <= ys[i+1]:
                left_idx = i
                break
        if left_idx is None and peak_idx > 0:
            seg = yy[:peak_idx]
            if np.any(np.isfinite(seg)):
                left_idx = int(np.nanargmin(seg))
        right_idx = None
        for i in range(peak_idx + 1, y.size - 1):
            if np.isfinite(ys[i-1:i+2]).all() and ys[i] <= ys[i-1] and ys[i] <= ys[i+1]:
                right_idx = i
                break
        if right_idx is None and peak_idx < y.size - 1:
            seg = yy[peak_idx+1:]
            if np.any(np.isfinite(seg)):
                right_idx = peak_idx + 1 + int(np.nanargmin(seg))
        if left_idx is None or right_idx is None or right_idx <= left_idx:
            return np.nan, np.nan, np.nan, left_idx, right_idx
        lx, rx = float(x[left_idx]), float(x[right_idx])
        return abs(rx - lx) * float(unit_scale), lx, rx, left_idx, right_idx


    def _calculate_threshold_width(self, x, y, peak_idx, threshold_percent, sign=1.0, unit_scale=1000.0):
        """Measure RAW-signal length from local minima -> peak -> local minimum.

        The threshold is a percentage of signal height, not an absolute amplitude.

        For the selected positive RAW peak:
          - MIN Left  = lowest RAW sample on the left side of the peak.
          - MAX       = selected RAW peak.
          - MIN Right = lowest RAW sample on the right side of the peak.

        Threshold convention requested by the user:
          For multi-defect ROI, each independently measured Length is multiplied by 2.
           50% -> measure at the halfway amplitude between each MIN and MAX.
            0% -> both sides converge to the MAX position.

        The left and right reference levels are calculated independently because
        the two local minima can have different amplitudes.
        """
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if x.size < 3 or y.size != x.size or peak_idx <= 0 or peak_idx >= x.size - 1:
            return (np.nan,) * 10

        try:
            pct = float(threshold_percent)
        except Exception:
            return (np.nan,) * 10
        if not np.isfinite(pct):
            return (np.nan,) * 10
        pct = min(100.0, max(0.0, pct))
        f = pct / 100.0

        # Work in the requested polarity; current RAW sizing uses sign=+1.
        p = sign * y
        peak_val_p = float(p[peak_idx])
        if not np.isfinite(peak_val_p):
            return (np.nan,) * 10

        left_seg = p[:peak_idx + 1]
        right_seg = p[peak_idx:]
        if not np.any(np.isfinite(left_seg)) or not np.any(np.isfinite(right_seg)):
            return (np.nan,) * 10

        # Lowest point on each side of the peak.  Include the peak endpoint so
        # the indices stay well-defined, but peak_idx itself cannot win unless
        # the side is completely flat.
        left_min_idx = int(np.nanargmin(left_seg))
        right_min_idx = int(peak_idx + np.nanargmin(right_seg))
        left_min_val_p = float(p[left_min_idx])
        right_min_val_p = float(p[right_min_idx])

        # Require the expected MIN -> MAX -> MIN ordering.
        if left_min_idx >= peak_idx or right_min_idx <= peak_idx:
            return (np.nan, np.nan, np.nan, np.nan, np.nan,
                    left_min_idx, right_min_idx,
                    sign * left_min_val_p, sign * peak_val_p, sign * right_min_val_p)

        # pct=100 means MIN level; pct=0 means MAX level.
        # level = MAX - f*(MAX-MIN)
        left_level_p = peak_val_p - f * (peak_val_p - left_min_val_p)
        right_level_p = peak_val_p - f * (peak_val_p - right_min_val_p)

        if pct >= 100.0 - 1e-12:
            left_x = float(x[left_min_idx])
            right_x = float(x[right_min_idx])
        elif pct <= 1e-12:
            left_x = right_x = float(x[peak_idx])
        else:
            # Find the crossing nearest the peak on each side, restricted to
            # the MIN-to-MAX branches selected above.
            left_x = np.nan
            for j in range(peak_idx - 1, left_min_idx - 1, -1):
                y1, y2 = p[j], p[j + 1]
                if not (np.isfinite(y1) and np.isfinite(y2)):
                    continue
                if (y1 - left_level_p) * (y2 - left_level_p) <= 0:
                    left_x = self._interpolated_crossing(x[j], y1, x[j + 1], y2, left_level_p)
                    break

            right_x = np.nan
            for j in range(peak_idx, right_min_idx):
                y1, y2 = p[j], p[j + 1]
                if not (np.isfinite(y1) and np.isfinite(y2)):
                    continue
                if (y1 - right_level_p) * (y2 - right_level_p) <= 0:
                    right_x = self._interpolated_crossing(x[j], y1, x[j + 1], y2, right_level_p)
                    break

        length_mm = ((right_x - left_x) * float(unit_scale)
                     if np.isfinite(left_x) and np.isfinite(right_x) and right_x >= left_x
                     else np.nan)

        # Convert levels/minima back to the original signal polarity for plotting.
        left_level = sign * left_level_p
        right_level = sign * right_level_p
        left_min_val = sign * left_min_val_p
        peak_val = sign * peak_val_p
        right_min_val = sign * right_min_val_p

        return (length_mm, left_x, right_x, left_level, right_level,
                left_min_idx, right_min_idx,
                left_min_val, peak_val, right_min_val)


    @staticmethod
    def _component_name_to_axis(name):
        return {'Bx': 'X', 'By': 'Y', 'Bz': 'Z'}.get(str(name), 'X')


    def _roi_sample_bounds(self, roi, x):
        """Return exact inclusive odometer indices for one ROI."""
        i1_saved = roi.get('sample_i1', np.nan)
        i2_saved = roi.get('sample_i2', np.nan)
        if np.isfinite(i1_saved) and np.isfinite(i2_saved):
            i1, i2 = int(i1_saved), int(i2_saved)
        else:
            i1 = int(np.nanargmin(np.abs(x - roi['x1'])))
            i2 = int(np.nanargmin(np.abs(x - roi['x2'])))
        if i2 < i1:
            i1, i2 = i2, i1
        i1 = max(0, min(i1, len(x) - 1))
        i2 = max(0, min(i2, len(x) - 1))
        return i1, i2


    def _analyze_length_component(self, ds, roi, axis, threshold_percent):
        """Analyze Length from Bx or Bz.

        Bx (normal method):
          RAW Bx -> percentage-threshold sizing.
          dBx/dx -> signed MAX/MIN P-P sizing.

        Bz (SWAPPED method):
          RAW Bz -> signed MAX/MIN P-P sizing.
          dBz/dx -> percentage-threshold sizing.

        MAX means the highest signed value and MIN means the lowest signed value;
        absolute magnitude is never used to choose extrema.
        """
        result = {'axis': axis}
        x_raw, z_raw = ds.get(axis, roi['odo'], 'Raw')
        i1, i2 = self._roi_sample_bounds(roi, x_raw)
        if i2 - i1 + 1 < 3:
            return result

        ch_indices = self._roi_channel_indices(roi, z_raw.shape[0])
        raw_crop = np.asarray(z_raw[ch_indices, i1:i2 + 1], dtype=float)
        xcrop = np.asarray(x_raw[i1:i2 + 1], dtype=float)
        if raw_crop.size == 0 or not np.any(np.isfinite(raw_crop)):
            return result

        # Select channel from the true positive RAW maximum for this component/ROI.
        flat_idx = int(np.nanargmax(raw_crop))
        local_ch, peak_idx = np.unravel_index(flat_idx, raw_crop.shape)
        selected_ch = int(ch_indices[local_ch] + 1)
        raw_y = np.asarray(raw_crop[local_ch], dtype=float)
        max_raw = float(raw_crop[local_ch, peak_idx])
        pct = min(100.0, max(0.0, float(threshold_percent)))

        # Mountain width: RAW signal base from nearest local valley on each side; no threshold.
        mountain_mm, mountain_lx, mountain_rx, mountain_li, mountain_ri = self._calculate_mountain_width(
            xcrop, raw_y, int(peak_idx), unit_scale=1000.0
        )

        # Full derivative on same selected channel.
        x_deriv, z_deriv = ds.get(axis, roi['odo'], 'Derivative')
        di1, di2 = self._roi_sample_bounds(roi, x_deriv)
        idx = selected_ch - 1
        deriv_y = np.asarray([], dtype=float)
        xdcrop = np.asarray([], dtype=float)
        if 0 <= idx < z_deriv.shape[0] and di2 - di1 + 1 >= 3:
            xdcrop = np.asarray(x_deriv[di1:di2 + 1], dtype=float)
            deriv_y = np.asarray(z_deriv[idx, di1:di2 + 1], dtype=float)

        # Defaults for both methods.
        thr_mm = lx = rx = ll = rl = lmv = peakv = rmv = np.nan
        lmi = rmi = None
        dmax_x = dmin_x = dmax_v = dmin_v = pp_base = pp_x2 = np.nan
        method_profile_pp = 'Derivative'
        method_profile_thr = 'Raw'

        if axis == 'Z':
            # TRUE SWAP FOR Bz:
            # 1) P-P from Bz RAW signed MAX/MIN.
            if np.any(np.isfinite(raw_y)):
                imax = int(np.nanargmax(raw_y))
                imin = int(np.nanargmin(raw_y))
                dmax_x, dmin_x = float(xcrop[imax]), float(xcrop[imin])
                dmax_v, dmin_v = float(raw_y[imax]), float(raw_y[imin])
                pp_base = abs(dmax_x - dmin_x) * 1000.0
                pp_x2 = pp_base

            # 2) @Threshold from dBz/dx using MIN-L -> MAX -> MIN-R.
            if deriv_y.size >= 3 and np.any(np.isfinite(deriv_y)):
                dpeak_idx = int(np.nanargmax(deriv_y))
                (thr_mm, lx, rx, ll, rl, lmi, rmi, lmv, peakv, rmv) = self._calculate_threshold_width(
                    xdcrop, deriv_y, dpeak_idx, pct, sign=1.0
                )
                peak_idx_for_thr = dpeak_idx
            else:
                peak_idx_for_thr = None
            method_profile_pp = 'Raw'
            method_profile_thr = 'Derivative'
        else:
            # NORMAL Bx:
            # 1) @Threshold from RAW Bx.
            (thr_mm, lx, rx, ll, rl, lmi, rmi, lmv, peakv, rmv) = self._calculate_threshold_width(
                xcrop, raw_y, int(peak_idx), pct, sign=1.0
            )
            peak_idx_for_thr = int(peak_idx)

            # 2) P-P from dBx/dx signed MAX/MIN.
            if deriv_y.size and np.any(np.isfinite(deriv_y)):
                imax = int(np.nanargmax(deriv_y))
                imin = int(np.nanargmin(deriv_y))
                dmax_x, dmin_x = float(xdcrop[imax]), float(xdcrop[imin])
                dmax_v, dmin_v = float(deriv_y[imax]), float(deriv_y[imin])
                pp_base = abs(dmax_x - dmin_x) * 1000.0
                pp_x2 = pp_base

        thr_x = xdcrop if axis == 'Z' else xcrop
        left_min_x = float(thr_x[lmi]) if isinstance(lmi, (int, np.integer)) and 0 <= lmi < thr_x.size else np.nan
        right_min_x = float(thr_x[rmi]) if isinstance(rmi, (int, np.integer)) and 0 <= rmi < thr_x.size else np.nan

        result.update({
            'i1': i1, 'i2': i2,
            'channel_indices': ch_indices.copy(),
            'channel_numbers': (ch_indices + 1).tolist(),
            'channel': selected_ch,
            'raw_crop': raw_crop,
            'x_raw': xcrop, 'raw': raw_y,
            'peak_idx': int(peak_idx),
            'max_raw': max_raw, 'max_raw_x': float(xcrop[peak_idx]),
            'threshold_percent': pct,
            'mountain_mm': mountain_mm,
            'mountain_left_x': mountain_lx, 'mountain_right_x': mountain_rx,
            'mountain_left_idx': mountain_li, 'mountain_right_idx': mountain_ri,
            'threshold_mm': thr_mm,
            'threshold_left_x': lx, 'threshold_right_x': rx,
            'threshold_left_level': ll, 'threshold_right_level': rl,
            'left_min_idx': lmi, 'right_min_idx': rmi,
            'left_min_x': left_min_x,
            'right_min_x': right_min_x,
            'left_min_value': lmv, 'peak_value': peakv, 'right_min_value': rmv,
            'threshold_peak_idx': peak_idx_for_thr,
            'x_deriv': xdcrop, 'deriv': deriv_y,
            'deriv_max_x': dmax_x, 'deriv_min_x': dmin_x,
            'deriv_max_value': dmax_v, 'deriv_min_value': dmin_v,
            'pp_base_mm': pp_base, 'pp_x2_mm': pp_x2,
            'pp_profile': method_profile_pp,
            'threshold_profile': method_profile_thr,
        })
        return result


    def _detect_multiple_length_defects(self, analysis, threshold_percent, max_defects=8, requested_count=None):
        """Detect consecutive positive RAW peaks inside one ROI and size each separately.

        This is intentionally a secondary analysis: the legacy single-defect fields stay
        unchanged, while ``analysis['multi_defects']`` contains one result per detected
        defect.  Adjacent defects are separated at the midpoint between neighbouring
        peaks so one peak cannot borrow the valley of the next peak.
        """
        x = np.asarray(analysis.get('x_raw', []), dtype=float)
        y = np.asarray(analysis.get('raw', []), dtype=float)
        if x.size < 7 or y.size != x.size or not np.any(np.isfinite(y)):
            analysis['multi_defects'] = []
            analysis['defect_count'] = 0
            return []

        yy = y.copy()
        med = float(np.nanmedian(yy))
        yy[~np.isfinite(yy)] = med
        # Light smoothing only for peak FINDING; sizing still uses original RAW data.
        sigma = max(0.7, min(2.0, yy.size / 120.0))
        ys = gaussian_filter1d(yy, sigma=sigma, mode='nearest')
        amp = float(np.nanpercentile(ys, 95) - np.nanpercentile(ys, 10))
        noise = float(np.nanmedian(np.abs(np.diff(ys) - np.nanmedian(np.diff(ys))))) if ys.size > 2 else 0.0
        prominence = max(0.10 * amp, 4.0 * noise, 1e-9)

        # Minimum separation ~2 mm where the odometer scale is usable.
        dx = float(np.nanmedian(np.abs(np.diff(x)))) if x.size > 1 else np.nan
        min_dist = max(2, int(round(0.002 / dx))) if np.isfinite(dx) and dx > 0 else 3
        # If the operator specifies a defect count, force selection of exactly that many
        # strongest physically separated peaks (where possible), rather than guessing the count.
        if requested_count is not None:
            try:
                requested_count = max(1, min(int(requested_count), 20))
            except Exception:
                requested_count = None

        peaks, props = find_peaks(ys, prominence=prominence, distance=min_dist)
        if requested_count is not None and requested_count > 1:
            # Relax prominence if needed so the requested number can be found.
            for factor in (1.0, 0.6, 0.35, 0.18, 0.08, 0.0):
                prom = prominence * factor if factor > 0 else None
                cand, _ = find_peaks(ys, prominence=prom, distance=min_dist) if prom is not None else find_peaks(ys, distance=min_dist)
                if cand.size >= requested_count:
                    peaks = cand
                    break
        if peaks.size == 0:
            peaks = np.asarray([int(np.nanargmax(ys))], dtype=int)

        # Reject very small peaks only in automatic-count mode. When the user gives
        # a count, preserve candidate peaks and choose the requested strongest ones.
        baseline = float(np.nanpercentile(ys, 10))
        heights = ys[peaks] - baseline
        strongest = float(np.nanmax(heights)) if heights.size else 0.0
        if strongest > 0 and requested_count is None:
            keep = heights >= 0.22 * strongest
            peaks = peaks[keep]
        if peaks.size == 0:
            peaks = np.asarray([int(np.nanargmax(ys))], dtype=int)

        # Keep exactly the operator-requested number (or automatic max), then restore
        # physical left-to-right order so D1, D2, D3 follow odometer position.
        keep_n = requested_count if requested_count is not None else max_defects
        if peaks.size > keep_n:
            order = np.argsort(ys[peaks])[-keep_n:]
            peaks = peaks[order]
        peaks = np.sort(peaks)

        # One defect is the legacy case; only advertise multi-defect mode for >=2.
        defects = []
        for k, pk in enumerate(peaks):
            left = 0 if k == 0 else int((peaks[k-1] + pk) // 2)
            right = y.size - 1 if k == peaks.size - 1 else int((pk + peaks[k+1]) // 2)
            left = max(0, min(left, int(pk) - 1))
            right = min(y.size - 1, max(right, int(pk) + 1))
            if right - left < 2:
                continue

            xs = x[left:right+1]
            ys_raw = y[left:right+1]
            local_pk = int(pk - left)
            vals = self._calculate_threshold_width(xs, ys_raw, local_pk, threshold_percent, sign=1.0)
            thr_mm, lx, rx, ll, rl, lmi, rmi, lmv, peakv, rmv = vals

            # Per-defect derivative P-P, restricted to the same basin.
            d = np.gradient(ys_raw, xs) if xs.size >= 3 else np.asarray([])
            dmax_x=dmin_x=dmax_v=dmin_v=pp_mm=np.nan
            if d.size and np.any(np.isfinite(d)):
                imax=int(np.nanargmax(d)); imin=int(np.nanargmin(d))
                dmax_x=float(xs[imax]); dmin_x=float(xs[imin])
                dmax_v=float(d[imax]); dmin_v=float(d[imin])
                pp_mm=abs(dmax_x-dmin_x)*1000.0

            # For a multi-defect ROI the requested Length algorithm is:
            # FINAL LENGTH = independently measured span x 2.
            # Keep the unmultiplied values too for traceability/debugging.
            multiplier = 2.0 if (requested_count is not None and int(requested_count) > 1) else 1.0
            thr_base_mm = float(thr_mm) if np.isfinite(thr_mm) else np.nan
            pp_base_local_mm = float(pp_mm) if np.isfinite(pp_mm) else np.nan
            thr_final_mm = thr_base_mm * multiplier if np.isfinite(thr_base_mm) else np.nan
            pp_final_mm = pp_base_local_mm * multiplier if np.isfinite(pp_base_local_mm) else np.nan

            defects.append({
                'defect_no': len(defects)+1,
                'peak_idx': int(pk), 'peak_x': float(x[pk]), 'peak_value': float(y[pk]),
                'segment_left_idx': left, 'segment_right_idx': right,
                'length_multiplier': multiplier,
                'threshold_base_mm': thr_base_mm,
                'threshold_mm': thr_final_mm,
                'threshold_left_x': float(lx) if np.isfinite(lx) else np.nan,
                'threshold_right_x': float(rx) if np.isfinite(rx) else np.nan,
                'threshold_left_level': float(ll) if np.isfinite(ll) else np.nan,
                'threshold_right_level': float(rl) if np.isfinite(rl) else np.nan,
                'left_min_value': float(lmv) if np.isfinite(lmv) else np.nan,
                'right_min_value': float(rmv) if np.isfinite(rmv) else np.nan,
                'deriv_pp_base_mm': pp_base_local_mm,
                'deriv_pp_mm': pp_final_mm,
                'deriv_max_x': dmax_x, 'deriv_min_x': dmin_x,
                'deriv_max_value': dmax_v, 'deriv_min_value': dmin_v,
            })

        analysis['multi_defects'] = defects
        analysis['defect_count'] = len(defects)
        return defects


    def _analyze_width_component(self, ds, roi, axis, threshold_percent):
        """Analyze Width from Bx or By.

        Bx (normal method):
          RAW Bx/channel -> percentage-threshold sizing.
          dBx/dChannel -> signed MAX/MIN P-P sizing.

        By (corrected method):
          RAW By/channel -> percentage-threshold sizing.
          dBy/dChannel -> signed MAX/MIN P-P sizing.
        """
        result = {'axis': axis}
        x_raw, z_raw = ds.get(axis, roi['odo'], 'Raw')
        i1, i2 = self._roi_sample_bounds(roi, x_raw)
        if i2 - i1 + 1 < 1:
            return result

        ch_indices = self._roi_channel_indices(roi, z_raw.shape[0])
        raw_crop = np.asarray(z_raw[ch_indices, i1:i2 + 1], dtype=float)
        xcrop = np.asarray(x_raw[i1:i2 + 1], dtype=float)
        if raw_crop.size == 0 or not np.any(np.isfinite(raw_crop)):
            return result

        flat_idx = int(np.nanargmax(raw_crop))
        local_ch, peak_idx = np.unravel_index(flat_idx, raw_crop.shape)
        selected_ch = int(ch_indices[local_ch] + 1)
        max_raw = float(raw_crop[local_ch, peak_idx])

        pitch_mm = float(roi.get('channel_pitch_mm', 6.0))
        pos_mm = np.arange(raw_crop.shape[0], dtype=float) * pitch_mm
        raw_profile = np.asarray(raw_crop[:, peak_idx], dtype=float)
        width_peak_idx = int(local_ch)
        pct = min(100.0, max(0.0, float(threshold_percent)))

        # Mountain width across channels from nearest local valley left/right; no threshold.
        mountain_mm, mountain_lp, mountain_rp, mountain_li, mountain_ri = self._calculate_mountain_width(
            pos_mm, raw_profile, width_peak_idx, unit_scale=1.0
        )

        deriv = np.asarray([], dtype=float)
        if raw_profile.size >= 3 and np.any(np.isfinite(raw_profile)):
            with np.errstate(divide='ignore', invalid='ignore'):
                deriv = np.gradient(raw_profile, pos_mm)
            deriv = np.asarray(deriv, dtype=float)
            deriv[~np.isfinite(deriv)] = 0.0

        thr_mm = lp = rp = ll = rl = lmv = peakv = rmv = np.nan
        lmi = rmi = None
        dmax_p = dmin_p = dmax_v = dmin_v = pp_base = pp_x2 = np.nan
        method_profile_pp = 'Derivative'
        method_profile_thr = 'Raw'

        # WIDTH mapping for both Bx and By:
        # 1) @Threshold from RAW component across channels.
        (thr_mm, lp, rp, ll, rl, lmi, rmi, lmv, peakv, rmv) = self._calculate_threshold_width(
            pos_mm, raw_profile, width_peak_idx, pct, sign=1.0, unit_scale=1.0
        )
        peak_idx_for_thr = width_peak_idx

        # 2) P-P from derivative across channels using signed MAX and signed MIN.
        if deriv.size and np.any(np.isfinite(deriv)):
            imax = int(np.nanargmax(deriv))
            imin = int(np.nanargmin(deriv))
            dmax_p, dmin_p = float(pos_mm[imax]), float(pos_mm[imin])
            dmax_v, dmin_v = float(deriv[imax]), float(deriv[imin])
            pp_base = abs(dmax_p - dmin_p)
            pp_x2 = pp_base
        method_profile_pp = 'Derivative'
        method_profile_thr = 'Raw'

        result.update({
            'i1': i1, 'i2': i2,
            'channel': selected_ch,
            'peak_sample_idx': int(peak_idx),
            'peak_x': float(xcrop[peak_idx]),
            'max_raw': max_raw,
            'pos_mm': pos_mm, 'raw': raw_profile,
            'peak_idx': width_peak_idx,
            'threshold_percent': pct,
            'mountain_mm': mountain_mm,
            'mountain_left_pos_mm': mountain_lp, 'mountain_right_pos_mm': mountain_rp,
            'mountain_left_idx': mountain_li, 'mountain_right_idx': mountain_ri,
            'threshold_mm': thr_mm,
            'threshold_left_pos_mm': lp, 'threshold_right_pos_mm': rp,
            'threshold_left_level': ll, 'threshold_right_level': rl,
            'left_min_idx': lmi, 'right_min_idx': rmi,
            'left_min_pos_mm': float(pos_mm[lmi]) if isinstance(lmi, (int, np.integer)) and 0 <= lmi < pos_mm.size else np.nan,
            'right_min_pos_mm': float(pos_mm[rmi]) if isinstance(rmi, (int, np.integer)) and 0 <= rmi < pos_mm.size else np.nan,
            'left_min_value': lmv, 'peak_value': peakv, 'right_min_value': rmv,
            'threshold_peak_idx': peak_idx_for_thr,
            'deriv': deriv,
            'deriv_max_pos_mm': dmax_p, 'deriv_min_pos_mm': dmin_p,
            'deriv_max_value': dmax_v, 'deriv_min_value': dmin_v,
            'pp_base_mm': pp_base, 'pp_x2_mm': pp_x2,
            'pp_profile': method_profile_pp,
            'threshold_profile': method_profile_thr,
        })
        return result


    def calculate_peak_length(self, roi):
        """Calculate all requested B-component sizing methods for one ROI.

        LENGTH profiles calculated and retained:
          - Bx vs x (RAW) and dBx/dx
          - Bz vs x (RAW) and dBz/dx

        WIDTH profiles calculated and retained:
          - Bx vs channel (RAW) and dBx/dChannel
          - By vs channel (RAW) and dBy/dChannel

        Report/table defaults are Bx for both Length and Width. Max Raw is always
        taken from Bx Raw. The embedded graphs can independently switch to Bz/By.
        """
        ds = next((d for d in self.datasets if d.path == roi['file_path']), None)
        if ds is None:
            roi['length_mm'] = np.nan
            roi['width_mm'] = np.nan
            return

        length_threshold = min(100.0, max(0.0, float(roi.get('length_threshold', roi.get('threshold', 50.0)))))
        width_threshold = min(100.0, max(0.0, float(roi.get('width_threshold', 50.0))))
        roi['length_threshold'] = length_threshold
        roi['width_threshold'] = width_threshold
        roi['threshold'] = length_threshold

        length_analysis = {}
        for axis in ('X', 'Z'):
            if axis in ds.signals:
                length_analysis[axis] = self._analyze_length_component(ds, roi, axis, length_threshold)
        width_analysis = {}
        for axis in ('X', 'Y'):
            if axis in ds.signals:
                width_analysis[axis] = self._analyze_width_component(ds, roi, axis, width_threshold)

        roi['length_analysis'] = length_analysis
        roi['width_analysis'] = width_analysis

        # Detect and size multiple consecutive defects inside the SAME ROI.
        # Bx RAW is the primary multi-defect profile because Bx RAW @Threshold
        # is the report default. Legacy single-defect outputs remain untouched.
        bx_multi = length_analysis.get('X', {}) or {}
        if bx_multi:
            requested = roi.get('requested_defect_count', 1)
            try:
                requested_n = max(1, int(requested))
            except Exception:
                requested_n = 1
            # Multi-defect rule: keep the operator-entered Length Threshold
            # (for example 50%).  For ROI containing >1 defect, each defect is
            # detected/sized independently and the final reported Length is
            # measured span x 2.  Do NOT force the threshold to 100%.
            multi_length_threshold = length_threshold
            bx_multi['multi_length_threshold_percent'] = multi_length_threshold
            bx_multi['multi_length_multiplier'] = 2.0 if requested_n > 1 else 1.0
            self._detect_multiple_length_defects(
                bx_multi, multi_length_threshold, requested_count=requested_n
            )
        roi['multi_defects'] = list(bx_multi.get('multi_defects', []))
        roi['defect_count'] = int(bx_multi.get('defect_count', 0) or 0)

        # Default values used in the ROI table/report.
        L = length_analysis.get('X') or length_analysis.get('Z') or {}
        W = width_analysis.get('X') or width_analysis.get('Y') or {}
        roi['analysis_length_axis'] = L.get('axis', 'X')
        roi['analysis_width_axis'] = W.get('axis', 'X')

        # Length aliases used by existing UI/export/classification code.
        roi['peak_channel'] = L.get('channel')
        roi['max_raw_signal'] = L.get('max_raw', np.nan)
        roi['max_abs_signal'] = L.get('max_raw', np.nan)
        roi['max_abs_signed_value'] = L.get('max_raw', np.nan)
        roi['max_raw_x'] = L.get('max_raw_x', np.nan)
        roi['max_abs_x'] = L.get('max_raw_x', np.nan)
        roi['length_pp_base_mm'] = L.get('pp_base_mm', np.nan)
        roi['length_pp_mm'] = L.get('pp_x2_mm', np.nan)
        roi['length_mm'] = L.get('pp_x2_mm', np.nan)
        roi['length_mm_unthresholded'] = L.get('pp_x2_mm', np.nan)
        roi['threshold_length_mm'] = L.get('threshold_mm', np.nan)
        roi['threshold_left_x'] = L.get('threshold_left_x', np.nan)
        roi['threshold_right_x'] = L.get('threshold_right_x', np.nan)
        roi['threshold_left_level'] = L.get('threshold_left_level', np.nan)
        roi['threshold_right_level'] = L.get('threshold_right_level', np.nan)
        roi['threshold_left_min_x'] = L.get('left_min_x', np.nan)
        roi['threshold_right_min_x'] = L.get('right_min_x', np.nan)
        roi['threshold_left_min_value'] = L.get('left_min_value', np.nan)
        roi['threshold_peak_value'] = L.get('peak_value', np.nan)
        roi['threshold_right_min_value'] = L.get('right_min_value', np.nan)
        roi['true_max_x'] = L.get('deriv_max_x', np.nan)
        roi['true_min_x'] = L.get('deriv_min_x', np.nan)
        roi['true_max_value'] = L.get('deriv_max_value', np.nan)
        roi['true_min_value'] = L.get('deriv_min_value', np.nan)
        roi['peak_pos_x'] = roi['true_max_x']
        roi['peak_neg_x'] = roi['true_min_x']
        roi['peak_pos_value'] = roi['true_max_value']
        roi['peak_neg_value'] = roi['true_min_value']
        roi['fwhm_mm'] = roi['threshold_length_mm']
        roi['length_fwhm_mm'] = roi['threshold_length_mm']

        # Width aliases used by existing UI/export/classification code.
        roi['width_peak_channel'] = W.get('channel')
        roi['width_peak_x'] = W.get('peak_x', np.nan)
        roi['width_profile_pos_mm'] = np.asarray(W.get('pos_mm', []), dtype=float)
        roi['width_profile_raw'] = np.asarray(W.get('raw', []), dtype=float)
        roi['width_profile_deriv'] = np.asarray(W.get('deriv', []), dtype=float)
        roi['threshold_width_mm'] = W.get('threshold_mm', np.nan)
        roi['width_threshold_left_pos_mm'] = W.get('threshold_left_pos_mm', np.nan)
        roi['width_threshold_right_pos_mm'] = W.get('threshold_right_pos_mm', np.nan)
        roi['width_threshold_left_level'] = W.get('threshold_left_level', np.nan)
        roi['width_threshold_right_level'] = W.get('threshold_right_level', np.nan)
        roi['width_threshold_left_min_pos_mm'] = W.get('left_min_pos_mm', np.nan)
        roi['width_threshold_right_min_pos_mm'] = W.get('right_min_pos_mm', np.nan)
        roi['width_threshold_left_min_value'] = W.get('left_min_value', np.nan)
        roi['width_threshold_peak_value'] = W.get('peak_value', np.nan)
        roi['width_threshold_right_min_value'] = W.get('right_min_value', np.nan)
        roi['width_deriv_max_pos_mm'] = W.get('deriv_max_pos_mm', np.nan)
        roi['width_deriv_min_pos_mm'] = W.get('deriv_min_pos_mm', np.nan)
        roi['width_deriv_max_value'] = W.get('deriv_max_value', np.nan)
        roi['width_deriv_min_value'] = W.get('deriv_min_value', np.nan)
        roi['width_pp_base_mm'] = W.get('pp_base_mm', np.nan)
        roi['width_pp_mm'] = W.get('pp_x2_mm', np.nan)
        roi['width_mm'] = W.get('pp_x2_mm', np.nan)
        roi['threshold_pass'] = True


    @staticmethod
    def _safe_float(value, default=np.nan):
        """Safely convert a value to finite float.

        Used by table display, project restore, and AI helpers.
        Returns ``default`` when conversion fails or the value is not finite.
        """
        try:
            value = float(value)
            return value if np.isfinite(value) else default
        except (TypeError, ValueError, OverflowError):
            return default


    def calculate_anomaly_dimension_class(self, roi):
        """Classify a metal-loss indication using the POF anomaly dimension classes.

        A is defined from nominal wall thickness t:
            A = 10 mm, if t < 10 mm
            A = t,     if t >= 10 mm

        The classification uses measured indication Length L and Width W.
        """
        L = float(roi.get('length_pp_mm', roi.get('length_mm', np.nan)))
        W = float(roi.get('width_pp_mm', roi.get('width_mm', np.nan)))
        global_t = self.get_global_wall_thickness()
        if np.isfinite(global_t):
            roi['wall_thickness_mm'] = global_t
        t = float(roi.get('wall_thickness_mm', np.nan))

        if not (np.isfinite(L) and np.isfinite(W) and np.isfinite(t)) or L <= 0 or W <= 0 or t <= 0:
            roi['A_mm'] = np.nan
            roi['L_over_A'] = np.nan
            roi['W_over_A'] = np.nan
            roi['anomaly_class'] = 'Set WT'
            return roi['anomaly_class']

        A = 10.0 if t < 10.0 else t
        lA = L / A
        wA = W / A
        ratio = L / W

        # POF anomaly dimension class definitions.
        if W >= 3.0 * A and L >= 3.0 * A:
            cls = 'General'
        elif W < A and L < A:
            cls = 'Pin-hole'
        elif W < A and L >= A:
            cls = 'Axial slotting'
        elif W >= A and L < A:
            cls = 'Circumferential slotting'
        elif A <= W < 3.0 * A and ratio >= 2.0:
            cls = 'Axial grooving'
        elif A <= L < 3.0 * A and ratio <= 0.5:
            cls = 'Circumferential grooving'
        elif (A <= W < 6.0 * A and A <= L < 6.0 * A
              and 0.5 < ratio < 2.0
              and not (W >= 3.0 * A and L >= 3.0 * A)):
            cls = 'Pitting'
        else:
            # This normally occurs exactly on an uncommon boundary or outside
            # the dimensional ranges covered by the standard class definitions.
            cls = 'Unclassified'

        roi['A_mm'] = A
        roi['L_over_A'] = lA
        roi['W_over_A'] = wA
        roi['anomaly_class'] = cls
        return cls


    def refresh_roi_tree_item(self, roi):
        if not self.tree.exists(str(roi['id'])):
            return
        length_text = (
            f"{roi.get('length_pp_mm', roi['length_mm']):.2f}"
            if np.isfinite(roi.get('length_mm', np.nan))
            else "N/A"
        )
        self.tree.item(
            str(roi['id']),
            values=self._roi_table_row_values(roi)
        )
        self._schedule_class_cell_overlays()


    def on_roi_selected(self):
        roi = self.get_selected_roi()
        if roi is None:
            self._clear_selected_signal_plot('Click an ROI in the ROI List to display its signal.')
            return
        self.length_threshold_var.set(f"{float(roi.get('length_threshold', roi.get('threshold', 50.0))):.6g}")
        self.roi_defect_count_var.set(int(roi.get('requested_defect_count', 1) or 1))
        self.width_threshold_var.set(f"{float(roi.get('width_threshold', 50.0)):.6g}")
        self.depth_var.set(str(roi.get('depth', '')))
        self.anomaly_class_var.set(str(roi.get('anomaly_class', 'Set WT')))
        self.ext_int_var.set(str(roi.get('ext_int', 'External')))
        self.length_selected_method_var.set(str(roi.get('length_selected_method', roi.get('best_length_source', 'Bx Length P-P')) or 'Bx Length P-P'))
        self.width_selected_method_var.set(str(roi.get('width_selected_method', roi.get('best_width_source', 'Bx Width P-P')) or 'Bx Width P-P'))

        # Recalculate BEFORE redraw so the C-scan marker and the lower signal
        # plot always refer to exactly the same newly calculated MAX/channel.
        self.calculate_peak_length(roi)
        self.refresh_roi_tree_item(roi)
        self.highlight_selected_roi()
        self.update_selected_signal_plot(roi)


    def _apply_sizing_methods_to_roi(self, roi, length_method, width_method):
        """Store the requested methods and immediately rebuild the selected values."""
        # Recalculate the underlying Bx/Bz/By sizing results first so the selected
        # value is always taken from the latest ROI signal/threshold settings.
        self.calculate_peak_length(roi)
        roi['length_selected_method'] = length_method
        roi['width_selected_method'] = width_method
        self._update_actual_comparison(roi)
        self.calculate_anomaly_dimension_class(roi)

        # The previous AI depth may have been calculated from another L/W pair.
        # Recalculate it when a trained model is available; otherwise leave the
        # depth result untouched and only update the selected dimensions.
        if self.ai_model is not None:
            try:
                self._predict_ai_depth_for_roi(roi)
            except Exception:
                pass

        self.refresh_roi_tree_item(roi)


    def apply_selected_sizing_methods(self):
        """Apply the chosen Length/Width methods to exactly one selected ROI."""
        roi = self.get_selected_roi()
        if roi is None:
            messagebox.showinfo(
                'Length / Width Selected',
                'Please click the ROI row in the table first, then press Apply to Selected ROI.\n\n'
                'To use the same methods for every defect, press Apply to All ROI.'
            )
            return

        length_method = self.length_selected_method_var.get().strip() or 'Bx Length P-P'
        width_method = self.width_selected_method_var.get().strip() or 'Bx Width P-P'
        self._apply_sizing_methods_to_roi(roi, length_method, width_method)

        # Force the row to remain selected/visible after refresh.
        iid = str(roi['id'])
        if self.tree.exists(iid):
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)

        self.status_var.set(
            f"{roi['name']} UPDATED: Length selected = {length_method} | "
            f"Width selected = {width_method}"
        )


    def apply_selected_sizing_methods_all(self):
        """Apply the chosen Length/Width methods to every ROI in the table."""
        if not self.rois:
            messagebox.showinfo('Length / Width Selected', 'There are no ROI to update.')
            return

        length_method = self.length_selected_method_var.get().strip() or 'Bx Length P-P'
        width_method = self.width_selected_method_var.get().strip() or 'Bx Width P-P'

        selected = self.tree.selection()
        selected_id = selected[0] if selected else None
        updated = 0
        for roi in self.rois:
            try:
                self._apply_sizing_methods_to_roi(roi, length_method, width_method)
                updated += 1
            except Exception:
                pass

        # Rebuild once to guarantee that every visible row reflects the new source.
        self.renumber_rois()
        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
            self.tree.focus(selected_id)
            self.tree.see(selected_id)

        self.status_var.set(
            f"UPDATED {updated}/{len(self.rois)} ROI: Length selected = {length_method} | "
            f"Width selected = {width_method}"
        )


    def apply_properties_to_selected(self):
        roi = self.get_selected_roi()
        if roi is None:
            messagebox.showinfo('ROI Properties', 'Select an ROI first.')
            return
        roi['depth'] = self.depth_var.get().strip()
        # Wall thickness is global and is already shared by all ROI.
        roi['wall_thickness_mm'] = self.get_global_wall_thickness()
        self.calculate_anomaly_dimension_class(roi)
        self.anomaly_class_var.set(str(roi.get('anomaly_class', 'Set WT')))
        roi['ext_int'] = self.ext_int_var.get().strip() or 'External'
        roi['length_selected_method'] = self.length_selected_method_var.get().strip() or 'Bx Length P-P'
        roi['width_selected_method'] = self.width_selected_method_var.get().strip() or 'Bx Width P-P'
        self._update_actual_comparison(roi)
        self.refresh_roi_tree_item(roi)
        self.status_var.set(
            f"{roi['name']}: Depth = {roi['depth'] or '-'} | "
            f"WT = {roi.get('wall_thickness_mm', np.nan):.3g} mm | "
            f"A = {roi.get('A_mm', np.nan):.3g} mm | "
            f"Class = {roi.get('anomaly_class', 'Set WT')} | {roi['ext_int']}"
        )


    def apply_threshold_to_selected(self):
        roi = self.get_selected_roi()
        if roi is None:
            messagebox.showinfo('Threshold', 'Select an ROI first.')
            return
        try:
            length_value = float(self.length_threshold_var.get())
            width_value = float(self.width_threshold_var.get())
        except ValueError:
            messagebox.showerror('Threshold', 'Length and Width thresholds must be numeric percentages from 0 to 100.')
            return
        if not (0.0 <= length_value <= 100.0) or not (0.0 <= width_value <= 100.0):
            messagebox.showerror('Threshold', 'Both thresholds must be between 0 and 100 %.')
            return

        try:
            defect_count = max(1, min(int(self.roi_defect_count_var.get()), 20))
        except Exception:
            messagebox.showerror('Defects in ROI', 'Defect count must be an integer from 1 to 20.')
            return
        self.roi_defect_count_var.set(defect_count)
        roi['requested_defect_count'] = defect_count
        roi['length_threshold'] = length_value
        roi['width_threshold'] = width_value
        roi['threshold'] = length_value  # legacy alias
        self.calculate_peak_length(roi)
        self.calculate_anomaly_dimension_class(roi)
        self.anomaly_class_var.set(str(roi.get('anomaly_class', 'Set WT')))
        self.refresh_roi_tree_item(roi)
        self.update_selected_signal_plot(roi)

        self.status_var.set(
            f"{roi['name']}: Length threshold = {length_value:.1f}% | "
            f"Width threshold = {width_value:.1f}% | "
            f"Length @ Thr = {roi.get('threshold_length_mm', np.nan):.2f} mm | "
            f"Width @ Thr = {roi.get('threshold_width_mm', np.nan):.2f} mm"
        )


    def delete_selected_roi(self):
        roi = self.get_selected_roi()
        if roi is None:
            return
        deleted_name = roi['name']
        self.rois = [r for r in self.rois if r['id'] != roi['id']]
        self.length_threshold_var.set('50.0')
        self.width_threshold_var.set('50.0')
        self.renumber_rois()
        self.redraw()
        self._clear_selected_signal_plot('Click an ROI in the ROI List to display its signal.')
        self.status_var.set(f"Deleted {deleted_name}. ROI list renumbered 1-{len(self.rois)}.")


    def clear_rois(self):
        if not self.rois:
            return
        if not messagebox.askyesno('Clear ROI', 'Delete all ROI?'):
            return
        self.rois.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.redraw()
        self._clear_selected_signal_plot('Click an ROI in the ROI List to display its signal.')


