from .common import *


class CscanMixin:
    def get_color_limits(self, z):
        try:
            vmin = float(self.vmin_var.get()) if self.vmin_var.get().strip() else None
        except ValueError:
            vmin = None
        try:
            vmax = float(self.vmax_var.get()) if self.vmax_var.get().strip() else None
        except ValueError:
            vmax = None
        if vmin is None or vmax is None:
            lo, hi = np.nanpercentile(z, [2, 98])
            if vmin is None:
                vmin = lo
            if vmax is None:
                vmax = hi
        if vmin >= vmax:
            vmin, vmax = float(np.nanmin(z)), float(np.nanmax(z))
        return vmin, vmax


    def get_color_norm(self, z):
        """Return a normalization where the chosen value is exactly yellow.

        RdYlGn_r places yellow at the colormap midpoint (0.5). TwoSlopeNorm
        maps vcenter to 0.5 while allowing unequal ranges below and above it.
        If Yellow is blank, the numeric midpoint of vmin/vmax is used.
        """
        vmin, vmax = self.get_color_limits(z)
        try:
            center_text = self.vcenter_var.get().strip()
            vcenter = float(center_text) if center_text else 0.5 * (vmin + vmax)
        except ValueError:
            vcenter = 0.5 * (vmin + vmax)

        # TwoSlopeNorm requires vmin < vcenter < vmax. If the requested yellow
        # value is outside the displayed range, safely fall back to midpoint.
        if not np.isfinite(vcenter) or not (vmin < vcenter < vmax):
            vcenter = 0.5 * (vmin + vmax)

        return vmin, vcenter, vmax, TwoSlopeNorm(vmin=vmin, vcenter=vcenter, vmax=vmax)


    def auto_color(self):
        self.vmin_var.set('')
        self.vmax_var.set('')
        # Keep a manually selected Yellow value. This lets Auto choose the
        # outer color limits while preserving the user's meaningful baseline.
        self.redraw(preserve_view=True)


    @staticmethod
    def _sample_edges(x):
        """Return cell edges whose centers are the actual odometer samples.

        This is important because imshow(extent=...) stretches the first/last
        samples to the plot edges, so a visually selected box may not contain
        the same samples that are later searched numerically.  pcolormesh with
        these edges keeps the C-scan cells and the raw data indices identical.
        """
        x = np.asarray(x, dtype=float)
        if x.size == 0:
            return np.asarray([], dtype=float)
        if x.size == 1:
            return np.asarray([x[0] - 0.5, x[0] + 0.5], dtype=float)
        mids = 0.5 * (x[:-1] + x[1:])
        edges = np.empty(x.size + 1, dtype=float)
        edges[1:-1] = mids
        edges[0] = x[0] - 0.5 * (x[1] - x[0])
        edges[-1] = x[-1] + 0.5 * (x[-1] - x[-2])
        return edges


    def _get_channel_start(self):
        """Return the physical channel number placed at display row 1."""
        n = int(getattr(self, '_n_channels', 0) or 0)
        if n <= 0:
            return 1
        try:
            start = int(self.channel_start_var.get())
        except Exception:
            start = 1
        start = ((start - 1) % n) + 1
        if self.channel_start_var.get() != start:
            self.channel_start_var.set(start)
        return start


    def _channel_display_order(self, n=None):
        """0-based physical channel indices in the current circular display order."""
        if n is None:
            n = int(getattr(self, '_n_channels', 0) or 0)
        n = int(n or 0)
        if n <= 0:
            return np.asarray([], dtype=int)
        start0 = self._get_channel_start() - 1
        return np.concatenate((np.arange(start0, n, dtype=int), np.arange(0, start0, dtype=int)))


    def _display_pos_for_channel(self, physical_channel):
        """Map a 1-based physical channel to its 1-based C-scan display row."""
        try:
            ch0 = int(physical_channel) - 1
        except Exception:
            return np.nan
        order = np.asarray(getattr(self, '_channel_display_order_cache', []), dtype=int)
        if order.size == 0:
            order = self._channel_display_order()
        hits = np.flatnonzero(order == ch0)
        return float(hits[0] + 1) if hits.size else np.nan


    def _on_channel_start_control(self, event=None):
        if self.current is None:
            return
        self._set_circular_channel_start(self.channel_start_var.get())


    def _set_circular_channel_start(self, start_channel, preserve_x=True):
        """Rotate channel order ONLY; never change the current zoom/view.

        The vertical C-scan scrollbar is used to move the circular seam between
        channels (for example 68,69,70,1,2,3).  It must NOT zoom the C-scan.
        Therefore the exact X and Y limits are captured before redraw and
        restored afterwards.
        """
        n = int(getattr(self, '_n_channels', 0) or 0)
        if n <= 0:
            return
        try:
            start = int(float(start_channel))
        except Exception:
            start = 1
        start = ((start - 1) % n) + 1

        # Preserve the exact visual window.  No autoscale / no zoom change.
        old_xlim = tuple(self.ax.get_xlim()) if hasattr(self, 'ax') else None
        old_ylim = tuple(self.ax.get_ylim()) if hasattr(self, 'ax') else None
        crop_was_on = self.selector is not None

        self.channel_start_var.set(start)
        self.redraw()

        # redraw() recreates the artist and normally restores the default view;
        # put the user's current view back exactly as it was.
        if old_xlim is not None:
            self.ax.set_xlim(*old_xlim)
        if old_ylim is not None:
            self.ax.set_ylim(*old_ylim)

        self.canvas.draw_idle()
        self._update_cscan_scrollbars()
        if crop_was_on:
            self.enable_crop()

        self.status_var.set(
            f'Channel seam moved: Bottom Ch {start}. View/zoom unchanged. '
            f'Use this to place Ch {n} next to Ch 1 before cropping.'
        )


    def _process_cscan_for_display(self, z):
        """Return a processed COPY for visualization only.

        ROI selection, Max Raw, Length/Width, threshold calculations, and all
        Bx/By/Bz numerical measurements continue to use the original dataset.

        Modes
        -----
        Raw
            No processing.
        Baseline Corrected
            Remove the median offset of each physical channel.
        Smooth
            Light 2-D Gaussian smoothing to make the color image visually
            continuous without changing the stored raw data.
        Defect Enhanced
            Channel-baseline correction + removal of slow variation along X +
            light Gaussian smoothing. This is intended to suppress sensor bands
            and large background drift so localized defects stand out.
        """
        data = np.asarray(z, dtype=float).copy()
        if data.size == 0:
            return data

        mode = self.display_processing_var.get().strip()
        finite = np.isfinite(data)
        if not np.all(finite):
            # Fill isolated non-finite values with each channel median only for display.
            med = np.nanmedian(data, axis=1, keepdims=True)
            data = np.where(finite, data, med)
            data[~np.isfinite(data)] = 0.0

        if mode == 'Raw':
            return data

        if mode == 'Baseline Corrected':
            baseline = np.median(data, axis=1, keepdims=True)
            return data - baseline

        if mode == 'Smooth':
            # sigma=(channel direction, odometer direction)
            return gaussian_filter(data, sigma=(0.65, 1.15), mode='nearest')

        if mode == 'Defect Enhanced':
            # 1) remove fixed Hall-sensor/channel offset
            corrected = data - np.median(data, axis=1, keepdims=True)

            # 2) remove slow-varying background along odometer direction.
            # Use a window that scales with the scan length but remains bounded.
            n_x = corrected.shape[1]
            sigma_bg = max(6.0, min(35.0, n_x / 40.0))
            background = gaussian_filter1d(corrected, sigma=sigma_bg, axis=1, mode='nearest')
            enhanced = corrected - background

            # 3) light smoothing: enough to join adjacent pixels, not enough to
            # materially change defect geometry in the display.
            enhanced = gaussian_filter(enhanced, sigma=(0.55, 0.9), mode='nearest')
            return enhanced

        return data


    def _draw_stacked_trace_cscan(self, x, z_plot, order):
        """Draw a grayscale stacked-trace / waterfall style C-scan.

        Each displayed row is one physical Hall channel.  The magnetic signal is
        centered by its own median and converted to a small vertical deflection
        around that channel row.  This reproduces the common MFL trace view where
        defects appear as aligned dark excursions across adjacent channels.

        This function is display-only: ROI calculations continue to use the
        original Bx/By/Bz arrays exactly as before.
        """
        data = np.asarray(z_plot, dtype=float)
        if data.ndim != 2 or data.size == 0:
            return

        # Remove DC offset independently for each trace so channel-to-channel
        # baseline differences do not dominate the stacked view.
        centers = np.nanmedian(data, axis=1, keepdims=True)
        centered = data - centers
        centered[~np.isfinite(centered)] = 0.0

        # Robust common amplitude scale.  Using a percentile avoids a single
        # spike flattening every other channel.  About +/-0.38 channel spacing
        # keeps neighboring traces visually separate, similar to the reference.
        abs_vals = np.abs(centered[np.isfinite(centered)])
        scale = float(np.nanpercentile(abs_vals, 98.0)) if abs_vals.size else 1.0
        if not np.isfinite(scale) or scale <= 1e-12:
            scale = 1.0
        gain = 0.38 / scale

        n_ch = data.shape[0]
        # faint channel baselines
        for row in range(1, n_ch + 1):
            self.ax.axhline(row, color='0.90', linewidth=0.35, zorder=0)

        # Plot all physical channels in the current circular display order.
        # Very thin gray/black lines intentionally mimic an inspection trace view.
        for row_idx in range(n_ch):
            y = (row_idx + 1) + centered[row_idx] * gain
            self.ax.plot(x, y, color='0.28', linewidth=0.45, alpha=0.78, zorder=1)

        # No meaningful colorbar in trace mode.
        self.cax.clear()
        self.cax.set_axis_off()


    def redraw(self, preserve_view=False):
        if self.current is None:
            return

        # Keep the user's exact C-scan view for display-only refreshes such as
        # Raw -> Smooth / Defect Enhanced or color-limit changes.
        # Dataset/axis/odometer/signal changes still call redraw() normally and
        # therefore start from the default full view.
        old_xlim = tuple(self.ax.get_xlim()) if preserve_view and hasattr(self, 'ax') else None
        old_ylim = tuple(self.ax.get_ylim()) if preserve_view and hasattr(self, 'ax') else None
        crop_was_on = bool(preserve_view and self.selector is not None)

        try:
            x, z = self.current.get(self.axis_var.get(), self.odo_var.get(), self.mode_var.get())
        except Exception as e:
            messagebox.showerror('Plot error', str(e))
            return

        self.disable_crop()
        self.ax.clear()

        # Display processing is intentionally separated from the source data.
        # All ROI measurements still read from self.current.get(...) directly.
        z_display = self._process_cscan_for_display(z)
        vmin, vcenter, vmax, color_norm = self.get_color_norm(z_display)

        x_edges = self._sample_edges(x)
        self._n_channels = int(z.shape[0])
        if self._n_channels <= 0:
            return
        # Rotate rows circularly.  This is the key feature: the physical order can
        # be displayed as ... N-1,N,1,2,... with no visual break at N/1.
        order = self._channel_display_order(self._n_channels)
        self._channel_display_order_cache = order.copy()
        z_plot = np.asarray(z_display[order, :], dtype=float)

        y_edges = np.arange(0.5, self._n_channels + 1.5, 1.0)
        self._current_x_edges = x_edges
        self.full_xlim = (float(x_edges[0]), float(x_edges[-1]))
        self.full_ylim = (0.5, self._n_channels + 0.5)
        view_type = self.cscan_view_var.get().strip()
        if view_type == 'Stacked Traces':
            self._draw_stacked_trace_cscan(x, z_plot, order)
            self.cbar = None
        else:
            im = self.ax.pcolormesh(
                x_edges, y_edges, z_plot, shading='flat',
                norm=color_norm, cmap='RdYlGn_r'
            )
            self.cax.clear()
            self.cax.set_axis_on()
            self.cbar = self.fig.colorbar(im, cax=self.cax)
            label = 'Magnetic signal' if self.mode_var.get() == 'Raw' else 'dSignal / dOdometer'
            self.cbar.set_label(label)

        self.ax.set_xlabel(f'Odometer {self.odo_var.get()} (m)')
        self.ax.set_ylabel('Physical Channel (circular display)')
        start = self._get_channel_start()
        self.ax.set_title(
            f'{self.current.name} | {self.axis_var.get()} axis | {self.mode_var.get()} | '
            f'{self.display_processing_var.get()} | {self.cscan_view_var.get()} | Bottom Ch {start} | Yellow={vcenter:.4g}'
        )
        visible = self._get_visible_channel_count()
        self.ax.set_ylim(0.5, min(self._n_channels + 0.5, 0.5 + visible))

        # Tick labels show PHYSICAL channel numbers even though row order is rotated.
        tick_step = max(1, int(np.ceil(visible / 16.0)))
        ticks = np.arange(1, min(self._n_channels, visible) + 1, tick_step, dtype=int)
        if ticks.size:
            labels = [str(int(order[t-1]) + 1) for t in ticks]
            self.ax.set_yticks(ticks)
            self.ax.set_yticklabels(labels)

        self._draw_existing_rois()
        self.draw_peak_markers_on_cscan()

        # Restore the exact zoom/pan window after the new C-scan image has been
        # created. This prevents display processing / color refresh from
        # jumping back to the default view.
        if preserve_view:
            if old_xlim is not None:
                self.ax.set_xlim(*old_xlim)
            if old_ylim is not None:
                self.ax.set_ylim(*old_ylim)

        self.canvas.draw_idle()
        self._update_cscan_scrollbars()
        if crop_was_on:
            self.enable_crop()
        self.status_var.set(
            f'{self.current.name}: {z.shape[0]} channels | Display = {self.display_processing_var.get()} | View = {self.cscan_view_var.get()} | Circular bottom channel = {start}. '
            f'Use Y scrollbar or Bottom Ch to rotate channels WITHOUT changing zoom; choose a start that puts Ch {z.shape[0]} and Ch 1 together before cropping.'
        )


    def _draw_single_roi_overlay(self, roi):
        """Draw only one ROI without clearing/redrawing the C-scan.

        This prevents visible refresh/flicker after a crop while preserving the
        exact zoom, pan, circular channel order, colormap and display processing.
        """
        if self.current is None:
            return
        if (roi.get('file_path') != self.current.path
                or roi.get('odo') != self.odo_var.get()):
            return

        order = np.asarray(getattr(self, '_channel_display_order_cache', []), dtype=int)
        if order.size == 0:
            order = self._channel_display_order()
        pos_of = {int(ch0): i + 1 for i, ch0 in enumerate(order)}

        inds = self._roi_channel_indices(roi, len(order))
        positions = sorted(pos_of[int(ch)] for ch in inds if int(ch) in pos_of)
        if not positions:
            return

        # Split into contiguous display groups in case the current circular
        # channel seam cuts through this ROI.
        groups = []
        g = [positions[0]]
        for p in positions[1:]:
            if p == g[-1] + 1:
                g.append(p)
            else:
                groups.append(g)
                g = [p]
        groups.append(g)

        for group in groups:
            y_bottom = float(group[0]) - 0.5
            y_top = float(group[-1]) + 0.5
            rect = Rectangle(
                (roi['x1'], y_bottom),
                roi['x2'] - roi['x1'],
                y_top - y_bottom,
                fill=False, linewidth=2.0
            )
            self.ax.add_patch(rect)
            self.roi_artists.append((roi, rect))

        # Put the ROI label at the top-left of the first visible group.
        first_group = groups[0]
        self.ax.text(
            roi['x1'], float(first_group[-1]) + 0.5, roi['name'],
            fontsize=9, va='bottom', ha='left'
        )


    def _draw_single_roi_peak_markers(self, roi):
        """Draw peak markers for one ROI only when the C-scan shows Derivative."""
        if self.current is None or self.mode_var.get() != 'Derivative':
            return
        if (roi.get('file_path') != self.current.path
                or roi.get('axis') != self.axis_var.get()
                or roi.get('odo') != self.odo_var.get()):
            return

        ch = roi.get('peak_channel')
        if ch is None:
            return

        order = np.asarray(getattr(self, '_channel_display_order_cache', []), dtype=int)
        if order.size == 0:
            order = self._channel_display_order()
        where = np.flatnonzero(order == (int(ch) - 1))
        if where.size == 0:
            return
        y = float(where[0] + 1)

        x_max = roi.get('true_max_x', roi.get('peak_pos_x', np.nan))
        x_min = roi.get('true_min_x', roi.get('peak_neg_x', np.nan))
        if np.isfinite(x_max):
            self.ax.plot(x_max, y, marker='^', markersize=9)
        if np.isfinite(x_min):
            self.ax.plot(x_min, y, marker='v', markersize=9)


    def _draw_existing_rois(self):
        self.roi_artists = []
        if self.current is None:
            return
        order = np.asarray(getattr(self, '_channel_display_order_cache', []), dtype=int)
        if order.size == 0:
            order = self._channel_display_order()
        pos_of = {int(ch0): i + 1 for i, ch0 in enumerate(order)}

        for roi in self.rois:
            if roi['file_path'] != self.current.path or roi['odo'] != self.odo_var.get():
                continue
            inds = self._roi_channel_indices(roi, len(order))
            positions = sorted(pos_of[int(ch)] for ch in inds if int(ch) in pos_of)
            if not positions:
                continue
            # If a later rotation cuts an ROI at the display edge, draw two boxes.
            groups=[]
            st=pr=positions[0]
            for p in positions[1:]:
                if p == pr + 1:
                    pr=p
                else:
                    groups.append((st,pr)); st=pr=p
            groups.append((st,pr))
            for gi,(p1,p2) in enumerate(groups):
                y1=p1-0.5; y2=p2+0.5
                rect = Rectangle((roi['x1'], y1), roi['x2'] - roi['x1'], y2 - y1,
                                 fill=False, linewidth=2.0)
                self.ax.add_patch(rect)
                if gi == 0:
                    self.ax.text(roi['x1'], y2, roi['name'], fontsize=9, va='bottom', ha='left')
                self.roi_artists.append((roi, rect))


    def _turn_off_toolbar_mode(self):
        # Matplotlib toolbar pan/zoom buttons are toggles. Turn any active mode off.
        try:
            mode = str(self.toolbar.mode).lower()
            if 'pan' in mode:
                self.toolbar.pan()
            elif 'zoom' in mode:
                self.toolbar.zoom()
        except Exception:
            pass


    def _get_visible_channel_count(self):
        """Return a valid count of consecutive channels to show."""
        n = int(getattr(self, '_n_channels', 0) or 0)
        if n <= 0:
            return 1
        try:
            visible = int(self.visible_channels_var.get())
        except Exception:
            visible = 20
        return max(1, min(n, visible))


    def _channel_pan_limits(self):
        """Return allowed lower-Y limits so edge channels can move into the plot center.

        The visible C-scan height remains fixed in channel units, but blank space is
        allowed below Channel 1 and above the final channel.  This means Channel 1
        can be positioned at the bottom, part way up, or exactly in the middle of
        the graph instead of always being clamped to the lower edge.
        """
        n = int(getattr(self, '_n_channels', 0) or 0)
        visible = self._get_visible_channel_count()
        if n <= 0:
            return 0.5, 0.5
        span = float(visible)
        # Channel centres are 1, 2, ... n.  To put Ch1 at the plot centre:
        # y_low + span/2 = 1  ->  y_low = 1 - span/2.
        min_low = 1.0 - span / 2.0
        # Symmetric upper end: allow the last channel to reach the plot centre.
        max_low = float(n) - span / 2.0
        if max_low < min_low:
            max_low = min_low
        return min_low, max_low


    def _current_channel_low(self):
        """Current lower Y limit, clamped to the free-pan range."""
        lo, hi = self._channel_pan_limits()
        y1, y2 = self.ax.get_ylim()
        low = min(float(y1), float(y2))
        return max(lo, min(hi, low))


    def _current_channel_start(self):
        """Approximate first physical channel currently visible (1-based).

        Kept for compatibility with older code.  When blank padding is visible,
        this returns the first real channel intersecting the view.
        """
        n = int(getattr(self, '_n_channels', 0) or 0)
        if n <= 0:
            return 1
        y1, y2 = sorted(map(float, self.ax.get_ylim()))
        return max(1, min(n, int(np.ceil(y1 + 0.5))))


    def _set_channel_window(self, lower_y, redraw=True):
        """Move the fixed-height C-scan window vertically.

        ``lower_y`` is the lower Y-axis limit, not a channel number.  It may be
        negative, intentionally leaving blank space below Channel 1 so Ch1 can be
        moved to the middle of the graph.
        """
        n = int(getattr(self, '_n_channels', 0) or 0)
        if n <= 0:
            return
        visible = self._get_visible_channel_count()
        lo, hi = self._channel_pan_limits()
        lower_y = max(lo, min(hi, float(lower_y)))
        # Snap to 1-channel increments while preserving half-channel alignment.
        lower_y = lo + round(lower_y - lo)
        lower_y = max(lo, min(hi, lower_y))
        self.ax.set_ylim(lower_y, lower_y + visible)
        if redraw:
            self.canvas.draw_idle()
        self._update_cscan_scrollbars()

        y1, y2 = sorted(map(float, self.ax.get_ylim()))
        first_real = max(1, int(np.ceil(y1 + 0.5)))
        last_real = min(n, int(np.floor(y2 - 0.5)))
        center_y = (y1 + y2) / 2.0
        self.status_var.set(
            f'C-scan Y view {y1:.1f} to {y2:.1f}; real channels {first_real}-{last_real}. '
            f'Plot center = Ch {center_y:.1f}. Vertical scrollbar moves channels through the graph.'
        )


    def _change_visible_channels(self):
        """Change the number of display rows without changing circular order."""
        if self.current is None:
            return
        visible = self._get_visible_channel_count()
        self.ax.set_ylim(0.5, min(self._n_channels + 0.5, 0.5 + visible))
        self.canvas.draw_idle()
        self._update_cscan_scrollbars()


    def _update_cscan_scrollbars(self):
        """Synchronize X pan and circular Y-channel rotation scrollbars."""
        if not hasattr(self, 'cscan_hscroll') or not hasattr(self, 'cscan_vscroll'):
            return
        if not hasattr(self, 'full_xlim'):
            return

        fx1, fx2 = sorted(map(float, self.full_xlim))
        x1, x2 = sorted(map(float, self.ax.get_xlim()))
        xspan = fx2 - fx1
        if xspan <= 0:
            xa, xb = 0.0, 1.0
        else:
            xa = max(0.0, min(1.0, (x1 - fx1) / xspan))
            xb = max(0.0, min(1.0, (x2 - fx1) / xspan))
            if xb < xa:
                xa, xb = xb, xa
        self.cscan_hscroll.set(xa, xb)

        n = max(1, int(getattr(self, '_n_channels', 1) or 1))
        start0 = self._get_channel_start() - 1
        thumb = max(0.05, min(0.25, 1.0 / max(4.0, n / 4.0)))
        if n <= 1:
            ya=0.0
        else:
            ya=(start0 / float(n-1)) * (1.0-thumb)
        self.cscan_vscroll.set(ya, min(1.0, ya+thumb))


    def _scroll_axis(self, orient, *args):
        """Move C-scan without changing zoom.

        Y scrollbar only rotates the circular channel order.
        X scrollbar only pans the existing X window.
        Neither scrollbar changes X-span or Y-span.
        """
        if self.current is None:
            return

        if orient == 'y':
            # Circular channel rotation: one unit moves the physical start channel
            # by one, wrapping N -> 1. This changes where the channel seam appears.
            n = int(getattr(self, '_n_channels', 0) or 0)
            if n <= 0:
                return
            start = self._get_channel_start()
            if args and args[0] == 'moveto':
                frac = max(0.0, min(1.0, float(args[1])))
                start = 1 + int(round(frac * (n - 1)))
            elif args and args[0] == 'scroll':
                count = int(args[1])
                what = args[2] if len(args) > 2 else 'units'
                step = max(1, int(round(self._get_visible_channel_count() * 0.8))) if what == 'pages' else 1
                start = ((start - 1 + count * step) % n) + 1
            else:
                return
            self._set_circular_channel_start(start, preserve_x=True)
            return

        # X scrollbar: continuous odometer pan behavior.
        full1, full2 = sorted(map(float, self.full_xlim))
        view1, view2 = sorted(map(float, self.ax.get_xlim()))
        full_span = full2 - full1
        view_span = view2 - view1
        if full_span <= 0 or view_span >= full_span:
            new1, new2 = full1, full2
        else:
            max_start = full2 - view_span
            if args and args[0] == 'moveto':
                frac = float(args[1])
                new1 = full1 + frac * full_span
                new1 = min(max_start, max(full1, new1))
            elif args and args[0] == 'scroll':
                count = int(args[1])
                what = args[2] if len(args) > 2 else 'units'
                step = view_span * (0.85 if what == 'pages' else 0.08)
                new1 = view1 + count * step
                new1 = min(max_start, max(full1, new1))
            else:
                return
            new2 = new1 + view_span

        self.ax.set_xlim(new1, new2)
        self.canvas.draw_idle()
        self._update_cscan_scrollbars()
        self.status_var.set('C-scan moved with horizontal scrollbar.')


    def _on_cscan_xscroll(self, *args):
        self._scroll_axis('x', *args)


    def _on_cscan_yscroll(self, *args):
        self._scroll_axis('y', *args)


    def enable_zoom(self):
        if self.current is None:
            return
        self.disable_crop()
        self._turn_off_toolbar_mode()
        self.toolbar.zoom()
        self.status_var.set('ZOOM mode: drag a box to zoom. Right-drag can zoom out depending on Matplotlib backend.')


    def enable_pan(self):
        if self.current is None:
            return
        self.disable_crop()
        self._turn_off_toolbar_mode()
        self.toolbar.pan()
        self.status_var.set('PAN mode: drag the C-scan to move left/right or up/down.')


    def stop_interaction(self):
        self.disable_crop()
        self._turn_off_toolbar_mode()
        self.status_var.set('Interaction stopped. Choose ROI, Zoom, or Pan mode.')


    def on_mouse_wheel_zoom(self, event):
        """Zoom C-scan with mouse wheel, centered at the mouse cursor."""
        if self.current is None or event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            return

        # Keep ROI selector available; wheel zoom does not conflict with left-drag ROI.
        xlim = self.ax.get_xlim()
        ylim = self.ax.get_ylim()
        x0, y0 = float(event.xdata), float(event.ydata)

        # Matplotlib scroll step: positive = wheel up, negative = wheel down.
        scale = 0.80 if event.step > 0 else 1.25

        new_x1 = x0 - (x0 - xlim[0]) * scale
        new_x2 = x0 + (xlim[1] - x0) * scale
        new_y1 = y0 - (y0 - ylim[0]) * scale
        new_y2 = y0 + (ylim[1] - y0) * scale

        # Do not zoom farther out than the complete dataset.
        if hasattr(self, 'full_xlim'):
            fx1, fx2 = sorted(self.full_xlim)
            if scale > 1:
                new_x1 = max(fx1, new_x1)
                new_x2 = min(fx2, new_x2)
        if hasattr(self, 'full_ylim'):
            fy1, fy2 = sorted(self.full_ylim)
            if scale > 1:
                new_y1 = max(fy1, new_y1)
                new_y2 = min(fy2, new_y2)

        if new_x2 > new_x1 and new_y2 > new_y1:
            self.ax.set_xlim(new_x1, new_x2)
            self.ax.set_ylim(new_y1, new_y2)
            self.canvas.draw_idle()
            self._update_cscan_scrollbars()
            self.status_var.set('Mouse wheel zoom. Use C-scan scrollbars or right-drag to move.')


    def on_mouse_press(self, event):
        """Start panning with the right mouse button."""
        if self.current is None or event.inaxes != self.ax or event.button != 3:
            return
        if event.xdata is None or event.ydata is None:
            return
        self._right_pan = {
            'x': float(event.xdata),
            'y': float(event.ydata),
            'xlim': self.ax.get_xlim(),
            'ylim': self.ax.get_ylim(),
        }


    def on_mouse_motion(self, event):
        """Pan while the right mouse button is held."""
        if self._right_pan is None or event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            return

        dx = float(event.xdata) - self._right_pan['x']
        dy = float(event.ydata) - self._right_pan['y']
        x1, x2 = self._right_pan['xlim']
        y1, y2 = self._right_pan['ylim']
        nx1, nx2 = x1 - dx, x2 - dx
        ny1, ny2 = y1 - dy, y2 - dy

        # Clamp pan to available C-scan data.
        if hasattr(self, 'full_xlim'):
            fx1, fx2 = sorted(self.full_xlim)
            width = nx2 - nx1
            if width <= fx2 - fx1:
                if nx1 < fx1:
                    nx1, nx2 = fx1, fx1 + width
                if nx2 > fx2:
                    nx1, nx2 = fx2 - width, fx2
        if hasattr(self, 'full_ylim'):
            fy1, fy2 = sorted(self.full_ylim)
            height = ny2 - ny1
            if height <= fy2 - fy1:
                if ny1 < fy1:
                    ny1, ny2 = fy1, fy1 + height
                if ny2 > fy2:
                    ny1, ny2 = fy2 - height, fy2

        self.ax.set_xlim(nx1, nx2)
        self.ax.set_ylim(ny1, ny2)
        self.canvas.draw_idle()
        self._update_cscan_scrollbars()


    def on_mouse_release(self, event):
        if event.button == 3 and self._right_pan is not None:
            self._right_pan = None
            self.status_var.set('View moved. Mouse wheel = zoom, right-drag = pan, left-drag in ROI mode = crop.')


    def reset_view(self):
        if self.current is None:
            return
        self.disable_crop()
        self._turn_off_toolbar_mode()
        if hasattr(self, 'full_xlim'):
            self.ax.set_xlim(*self.full_xlim)
        self.channel_start_var.set(1)
        self.redraw()
        if hasattr(self, 'full_xlim'):
            self.ax.set_xlim(*self.full_xlim)
        visible = self._get_visible_channel_count()
        self.ax.set_ylim(0.5, min(self._n_channels + 0.5, 0.5 + visible))
        self.canvas.draw_idle()
        self._update_cscan_scrollbars()
        self.status_var.set('View reset: circular display starts from physical Channel 1.')


    def enable_crop(self):
        if self.current is None:
            return
        self.disable_crop()
        self._turn_off_toolbar_mode()
        self.selector = RectangleSelector(
            self.ax, self.on_select_roi,
            useblit=True,
            button=[1],
            minspanx=2,
            minspany=1,
            spancoords='pixels',
            interactive=False,
        )
        self.status_var.set('ROI mode ON: drag a rectangle around a defect. You can repeat to create multiple ROI.')


    def disable_crop(self):
        if self.selector is not None:
            try:
                self.selector.set_active(False)
                self.selector.disconnect_events()
            except Exception:
                pass
            self.selector = None


    def draw_peak_markers_on_cscan(self):
        """
        Draw MAX/MIN markers only when the main C-scan is in Derivative mode.
        This prevents derivative peak markers from being visually compared
        against a Raw-signal color map.
        """
        if self.current is None:
            return

        # In Raw mode, show each ROI's independently detected raw MAX so the
        # selected channel can be visually checked box-by-box.
        if self.mode_var.get() == 'Raw':
            for roi in self.rois:
                if (
                    roi['file_path'] != self.current.path
                    or roi['axis'] != self.axis_var.get()
                    or roi['odo'] != self.odo_var.get()
                ):
                    continue
                ch = roi.get('peak_channel')
                x_max_raw = roi.get('max_raw_x', roi.get('max_abs_x', np.nan))
                val = roi.get('max_raw_signal', roi.get('max_abs_signal', np.nan))
                if ch is None or not np.isfinite(x_max_raw):
                    continue
                ydisp = self._display_pos_for_channel(ch)
                if not np.isfinite(ydisp):
                    continue
                self.ax.plot(x_max_raw, ydisp, marker='o', markersize=8, markerfacecolor='none', markeredgewidth=2)
                self.ax.annotate(
                    f"{roi['name']} MAX {val:.3g}\nCh {ch}",
                    xy=(x_max_raw, ydisp), xytext=(7, 8), textcoords='offset points',
                    fontsize=8, ha='left', va='bottom'
                )
            return

        if self.mode_var.get() != 'Derivative':
            return

        for roi in self.rois:
            if (
                roi['file_path'] != self.current.path
                or roi['axis'] != self.axis_var.get()
                or roi['odo'] != self.odo_var.get()
            ):
                continue

            ch = roi.get('peak_channel')
            x_max = roi.get('true_max_x', roi.get('peak_pos_x', np.nan))
            x_min = roi.get('true_min_x', roi.get('peak_neg_x', np.nan))

            if ch is None:
                continue
            ydisp = self._display_pos_for_channel(ch)
            if not np.isfinite(ydisp):
                continue

            if np.isfinite(x_max):
                self.ax.plot(x_max, ydisp, marker='^', markersize=9)
                self.ax.annotate(
                    f"MAX {roi.get('true_max_value', np.nan):.3g}\n"
                    f"Ch {ch}\n"
                    f"x={x_max:.6f} m",
                    xy=(x_max, ydisp),
                    xytext=(7, 12),
                    textcoords='offset points',
                    fontsize=8,
                    ha='left',
                    va='bottom',
                )

            if np.isfinite(x_min):
                self.ax.plot(x_min, ydisp, marker='v', markersize=9)
                self.ax.annotate(
                    f"MIN {roi.get('true_min_value', np.nan):.3g}\n"
                    f"Ch {ch}\n"
                    f"x={x_min:.6f} m",
                    xy=(x_min, ydisp),
                    xytext=(7, -12),
                    textcoords='offset points',
                    fontsize=8,
                    ha='left',
                    va='top',
                )


    def highlight_selected_roi(self):
        roi = self.get_selected_roi()
        if roi is None:
            return
        # If ROI belongs to another file, switch file/axis/mode/odo automatically
        for i, ds in enumerate(self.datasets):
            if ds.path == roi['file_path']:
                if self.current is None or self.current.path != ds.path:
                    self.file_combo.current(i)
                    self.current = ds
                break
        self.axis_var.set(roi['axis'])
        self.mode_var.set(roi['mode'])
        self.odo_var.set(roi['odo'])
        self.redraw()
        self.ax.set_xlim(roi['x1'] - 0.02 * max(roi['x2'] - roi['x1'], 1e-6), roi['x2'] + 0.02 * max(roi['x2'] - roi['x1'], 1e-6))
        self.ax.set_ylim(max(0.5, roi['y1'] - 1), roi['y2'] + 1)
        self.canvas.draw_idle()
        self._update_cscan_scrollbars()
        if np.isfinite(roi.get('length_mm', np.nan)):
            self.status_var.set(
                f"Selected {roi['name']} | "
                f"Max Raw = {roi.get('max_abs_signal', np.nan):.4g} "
                f"({roi.get('display_mode_for_absmax', roi.get('mode', ''))}) | "
                f"Ch {roi.get('peak_channel', '-')} @ {roi.get('max_abs_x', np.nan):.6f} m | "
                f"MAX d/dx {roi.get('peak_pos_value', np.nan):.4g} | "
                f"MIN d/dx {roi.get('peak_neg_value', np.nan):.4g} | "
                f"Length {roi['length_mm']:.2f} mm | Length @ Threshold {roi.get('threshold_length_mm', roi.get('fwhm_mm', np.nan)):.2f} mm"
            )
        else:
            self.status_var.set(f"Selected {roi['name']}: peak length not detected.")


