from .common import *


class UiMixin:
    def switch_lower_view(self):
        is_3d = self.lower_view_var.get() == '3D Pipe Defect'
        if is_3d:
            self.signal_host.pack_forget()
            self.pipe_3d_host.pack(fill=tk.BOTH, expand=True)
            if hasattr(self, '_refresh_embedded_3d'):
                self._refresh_embedded_3d()
        else:
            self.pipe_3d_host.pack_forget()
            self.signal_host.pack(fill=tk.BOTH, expand=True)
            self.signal_canvas.draw_idle()

    def _build_ui(self):
        # Two-row top toolbar to avoid crowding on normal-width screens.
        top = ttk.Frame(self.root, padding=6)
        top.pack(side=tk.TOP, fill=tk.X)
        top_row1 = ttk.Frame(top)
        top_row1.pack(side=tk.TOP, fill=tk.X, pady=(0, 3))
        top_row2 = ttk.Frame(top)
        top_row2.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top_row1, text='Open CSV File(s)', command=self.open_files).pack(side=tk.LEFT, padx=3)
        ttk.Button(top_row1, text='Save Project', command=self.save_project).pack(side=tk.LEFT, padx=3)
        ttk.Button(top_row1, text='Load Project', command=self.load_project).pack(side=tk.LEFT, padx=3)

        ttk.Label(top_row1, text='File:').pack(side=tk.LEFT, padx=(10, 3))
        self.file_combo = ttk.Combobox(top_row1, textvariable=self.file_var, state='readonly', width=24)
        self.file_combo.pack(side=tk.LEFT, padx=3)
        self.file_combo.bind('<<ComboboxSelected>>', lambda e: self.change_dataset())

        ttk.Label(top_row1, text='Axis:').pack(side=tk.LEFT, padx=(10, 3))
        axis_combo = ttk.Combobox(top_row1, textvariable=self.axis_var, state='readonly', width=5,
                                  values=['X', 'Y', 'Z'])
        axis_combo.pack(side=tk.LEFT)
        axis_combo.bind('<<ComboboxSelected>>', lambda e: self.redraw(preserve_view=True))

        ttk.Label(top_row1, text='Signal:').pack(side=tk.LEFT, padx=(10, 3))
        mode_combo = ttk.Combobox(top_row1, textvariable=self.mode_var, state='readonly', width=11,
                                  values=['Raw', 'Derivative'])
        mode_combo.pack(side=tk.LEFT)
        mode_combo.bind('<<ComboboxSelected>>', lambda e: self.redraw())

        ttk.Label(top_row1, text='Odometer:').pack(side=tk.LEFT, padx=(10, 3))
        odo_combo = ttk.Combobox(top_row1, textvariable=self.odo_var, state='readonly', width=4,
                                 values=[1, 2, 3])
        odo_combo.pack(side=tk.LEFT)
        odo_combo.bind('<<ComboboxSelected>>', self.on_odometer_changed)

        ttk.Label(top_row1, text='Channels shown:').pack(side=tk.LEFT, padx=(10, 3))
        ch_view_combo = ttk.Combobox(
            top_row1, textvariable=self.visible_channels_var, state='readonly', width=4,
            values=[5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100]
        )
        ch_view_combo.pack(side=tk.LEFT)
        ch_view_combo.bind('<<ComboboxSelected>>', lambda e: self._change_visible_channels())

        ttk.Label(top_row1, text='Bottom Ch:').pack(side=tk.LEFT, padx=(10, 3))
        self.channel_start_spin = ttk.Spinbox(
            top_row1, textvariable=self.channel_start_var, from_=1, to=9999, width=5,
            command=self._on_channel_start_control
        )
        self.channel_start_spin.pack(side=tk.LEFT)
        self.channel_start_spin.bind('<Return>', self._on_channel_start_control)
        self.channel_start_spin.bind('<FocusOut>', self._on_channel_start_control)

        ttk.Label(top_row2, text='Display:').pack(side=tk.LEFT, padx=(10, 3))
        display_combo = ttk.Combobox(
            top_row2, textvariable=self.display_processing_var, state='readonly', width=18,
            values=['Raw', 'Baseline Corrected', 'Smooth', 'Defect Enhanced']
        )
        display_combo.pack(side=tk.LEFT)
        display_combo.bind('<<ComboboxSelected>>', lambda e: self.redraw(preserve_view=True))

        ttk.Label(top_row2, text='View:').pack(side=tk.LEFT, padx=(10, 3))
        view_combo = ttk.Combobox(
            top_row2, textvariable=self.cscan_view_var, state='readonly', width=16,
            values=['Color C-scan', 'Stacked Traces']
        )
        view_combo.pack(side=tk.LEFT)
        view_combo.bind('<<ComboboxSelected>>', lambda e: self.redraw(preserve_view=True))

        ttk.Checkbutton(
            top_row2,
            text='Auto Sensor Offset',
            variable=self.auto_sensor_offset_var,
            command=self.apply_auto_sensor_offset
        ).pack(side=tk.LEFT, padx=(10, 3))

        ttk.Label(top_row2, text='Global Offset:').pack(side=tk.LEFT, padx=(10, 3))
        offset_entry = ttk.Entry(top_row2, textvariable=self.global_offset_var, width=7)
        offset_entry.pack(side=tk.LEFT)
        offset_entry.bind('<Return>', self.apply_global_offset)
        offset_entry.bind('<FocusOut>', self.apply_global_offset)
        ttk.Button(top_row2, text='Apply Offset', command=self.apply_global_offset).pack(side=tk.LEFT, padx=3)

        ttk.Label(top_row2, text='Color min:').pack(side=tk.LEFT, padx=(10, 3))
        ttk.Entry(top_row2, textvariable=self.vmin_var, width=9).pack(side=tk.LEFT)
        ttk.Label(top_row2, text='max:').pack(side=tk.LEFT, padx=(5, 3))
        ttk.Entry(top_row2, textvariable=self.vmax_var, width=9).pack(side=tk.LEFT)
        ttk.Label(top_row2, text='Yellow:').pack(side=tk.LEFT, padx=(5, 3))
        center_entry = ttk.Entry(top_row2, textvariable=self.vcenter_var, width=9)
        center_entry.pack(side=tk.LEFT)
        center_entry.bind('<Return>', lambda e: self.redraw(preserve_view=True))
        ttk.Button(top_row2, text='Apply', command=lambda: self.redraw(preserve_view=True)).pack(side=tk.LEFT, padx=3)
        ttk.Button(top_row2, text='Auto', command=self.auto_color).pack(side=tk.LEFT, padx=3)

        main = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        plot_frame = ttk.Frame(main)

        # Scrollable RIGHT control panel.  The previous right_frame was added
        # directly to the Panedwindow, so controls near the bottom could fall
        # below the screen and become unreachable.  Put all right-side controls
        # inside a Canvas + vertical Scrollbar instead.
        right_scroll_host = ttk.Frame(main, width=360)
        main.add(plot_frame, weight=4)
        main.add(right_scroll_host, weight=1)

        self.right_scroll_canvas = tk.Canvas(
            right_scroll_host, highlightthickness=0, borderwidth=0
        )
        self.right_vscroll = ttk.Scrollbar(
            right_scroll_host, orient=tk.VERTICAL, command=self.right_scroll_canvas.yview
        )
        self.right_scroll_canvas.configure(yscrollcommand=self.right_vscroll.set)
        self.right_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.right_scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        right_frame = ttk.Frame(self.right_scroll_canvas)
        self._right_scroll_window = self.right_scroll_canvas.create_window(
            (0, 0), window=right_frame, anchor='nw'
        )

        def _sync_right_scrollregion(event=None):
            bbox = self.right_scroll_canvas.bbox('all')
            if bbox:
                self.right_scroll_canvas.configure(scrollregion=bbox)

        def _sync_right_width(event):
            # Make the inner controls follow the visible width of the right pane.
            self.right_scroll_canvas.itemconfigure(
                self._right_scroll_window, width=max(1, event.width)
            )

        right_frame.bind('<Configure>', _sync_right_scrollregion)
        self.right_scroll_canvas.bind('<Configure>', _sync_right_width)

        # Mouse-wheel scrolling is active while the pointer is over the right panel.
        # Use bind_all only while hovered so the C-scan wheel zoom keeps working.
        def _right_wheel(event):
            delta = getattr(event, 'delta', 0)
            if delta:
                steps = -1 if delta > 0 else 1
            else:
                num = getattr(event, 'num', None)
                steps = -1 if num == 4 else 1
            self.right_scroll_canvas.yview_scroll(steps * 3, 'units')
            return 'break'

        def _bind_right_wheel(event=None):
            self.root.bind_all('<MouseWheel>', _right_wheel)
            self.root.bind_all('<Button-4>', _right_wheel)
            self.root.bind_all('<Button-5>', _right_wheel)

        def _unbind_right_wheel(event=None):
            self.root.unbind_all('<MouseWheel>')
            self.root.unbind_all('<Button-4>')
            self.root.unbind_all('<Button-5>')

        right_scroll_host.bind('<Enter>', _bind_right_wheel)
        right_scroll_host.bind('<Leave>', _unbind_right_wheel)
        self.right_scroll_canvas.bind('<Enter>', _bind_right_wheel)
        self.right_scroll_canvas.bind('<Leave>', _unbind_right_wheel)
        right_frame.bind('<Enter>', _bind_right_wheel)
        right_frame.bind('<Leave>', _unbind_right_wheel)

        # REAL vertically-scrollable left analysis area.
        # The C-scan and selected-signal plots are stacked in a Tk Canvas so the
        # user can move down to the lower plots even on a short screen.
        left_scroll_host = ttk.Frame(plot_frame)
        left_scroll_host.pack(fill=tk.BOTH, expand=True)

        self.left_scroll_canvas = tk.Canvas(
            left_scroll_host, highlightthickness=0, borderwidth=0
        )
        self.left_vscroll = ttk.Scrollbar(
            left_scroll_host, orient=tk.VERTICAL, command=self.left_scroll_canvas.yview
        )
        self.left_scroll_canvas.configure(yscrollcommand=self.left_vscroll.set)
        self.left_vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.left_scroll_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.left_scroll_inner = ttk.Frame(self.left_scroll_canvas)
        self._left_scroll_window = self.left_scroll_canvas.create_window(
            (0, 0), window=self.left_scroll_inner, anchor='nw'
        )

        # Give both plot sections real requested heights.  This is important:
        # without a content height larger than the viewport, a scrollbar has
        # nothing to scroll.
        cscan_frame = ttk.Frame(self.left_scroll_inner, height=650)
        cscan_frame.pack(fill=tk.X, expand=False)
        cscan_frame.pack_propagate(False)

        signal_frame = ttk.LabelFrame(
            self.left_scroll_inner, text='Selected ROI Signal', padding=4, height=760
        )
        signal_frame.pack(fill=tk.X, expand=False, pady=(6, 8))
        signal_frame.pack_propagate(False)

        def _sync_left_scrollregion(event=None):
            self.left_scroll_canvas.configure(
                scrollregion=self.left_scroll_canvas.bbox('all')
            )

        def _sync_left_width(event):
            # Keep the embedded frame the same width as the visible canvas.
            self.left_scroll_canvas.itemconfigure(
                self._left_scroll_window, width=max(1, event.width)
            )

        self.left_scroll_inner.bind('<Configure>', _sync_left_scrollregion)
        self.left_scroll_canvas.bind('<Configure>', _sync_left_width)

        # Shift + mouse wheel always scrolls the page vertically.
        # Normal wheel on the C-scan remains reserved for C-scan zoom.
        def _scroll_left_page(event):
            delta = getattr(event, 'delta', 0)
            if delta:
                steps = -1 if delta > 0 else 1
            else:
                num = getattr(event, 'num', None)
                steps = -1 if num == 4 else 1
            self.left_scroll_canvas.yview_scroll(steps * 3, 'units')
            return 'break'

        self.left_scroll_canvas.bind('<Shift-MouseWheel>', _scroll_left_page)
        self.left_scroll_inner.bind('<Shift-MouseWheel>', _scroll_left_page)
        cscan_frame.bind('<Shift-MouseWheel>', _scroll_left_page)
        signal_frame.bind('<Shift-MouseWheel>', _scroll_left_page)
        # Linux/X11 wheel compatibility.
        self.left_scroll_canvas.bind('<Shift-Button-4>', _scroll_left_page)
        self.left_scroll_canvas.bind('<Shift-Button-5>', _scroll_left_page)

        self.fig, self.ax = plt.subplots(figsize=(11, 7))

        # Fixed plot geometry: repeated redraws must not shrink the C-scan.
        self.ax.set_position([0.08, 0.11, 0.80, 0.82])
        self.cax = self.fig.add_axes([0.90, 0.11, 0.022, 0.82])
        self.cbar = None

        # C-scan plot area with its own horizontal and vertical scrollbars.
        # X pans odometer; Y rotates the physical channel order circularly.
        cscan_plot_host = ttk.Frame(cscan_frame)
        cscan_plot_host.pack(fill=tk.BOTH, expand=True)

        self.cscan_vscroll = ttk.Scrollbar(
            cscan_plot_host, orient=tk.VERTICAL, command=self._on_cscan_yscroll
        )
        self.cscan_hscroll = ttk.Scrollbar(
            cscan_plot_host, orient=tk.HORIZONTAL, command=self._on_cscan_xscroll
        )

        self.canvas = FigureCanvasTkAgg(self.fig, master=cscan_plot_host)
        cscan_widget = self.canvas.get_tk_widget()

        # Grid layout keeps the scrollbars attached directly to the C-scan.
        cscan_widget.grid(row=0, column=0, sticky='nsew')
        self.cscan_vscroll.grid(row=0, column=1, sticky='ns')
        self.cscan_hscroll.grid(row=1, column=0, sticky='ew')
        cscan_plot_host.rowconfigure(0, weight=1)
        cscan_plot_host.columnconfigure(0, weight=1)

        self.toolbar = NavigationToolbar2Tk(self.canvas, cscan_frame, pack_toolbar=False)
        self.toolbar.update()
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)

        # Embedded signal viewer shown automatically when an ROI row is clicked.
        # Left column  = Length sizing along odometer direction.
        # Right column = Width sizing across channels.
        self.signal_fig = plt.Figure(figsize=(10, 4.8))
        self.signal_ax_raw = self.signal_fig.add_subplot(221)
        self.signal_ax_deriv = self.signal_fig.add_subplot(223, sharex=self.signal_ax_raw)
        self.signal_ax_width_raw = self.signal_fig.add_subplot(222)
        self.signal_ax_width_deriv = self.signal_fig.add_subplot(224, sharex=self.signal_ax_width_raw)
        self.signal_fig.subplots_adjust(left=0.07, right=0.98, bottom=0.12, top=0.90, hspace=0.25, wspace=0.22)
        view_bar = ttk.Frame(signal_frame)
        view_bar.pack(side=tk.TOP, fill=tk.X, pady=(0, 4))
        ttk.Label(view_bar, text='Lower-left view:').pack(side=tk.LEFT, padx=4)
        self.lower_view_var = tk.StringVar(value='Signal Graph')
        view_combo = ttk.Combobox(view_bar, textvariable=self.lower_view_var,
                                  state='readonly', width=18,
                                  values=['Signal Graph', '3D Pipe Defect'])
        view_combo.pack(side=tk.LEFT, padx=4)
        view_combo.bind('<<ComboboxSelected>>', lambda event: self.switch_lower_view())
        self.signal_host = ttk.Frame(signal_frame)
        self.signal_host.pack(fill=tk.BOTH, expand=True)
        self.pipe_3d_host = ttk.Frame(signal_frame)
        signal_controls = ttk.Frame(self.signal_host)
        signal_controls.pack(side=tk.TOP, fill=tk.X, padx=2, pady=(0, 4))

        ttk.Label(signal_controls, text='Length signal:').pack(side=tk.LEFT, padx=(2, 3))
        length_signal_combo = ttk.Combobox(
            signal_controls, textvariable=self.length_plot_component_var,
            state='readonly', width=5, values=['Bx', 'Bz']
        )
        length_signal_combo.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(signal_controls, text='Width signal:').pack(side=tk.LEFT, padx=(2, 3))
        width_signal_combo = ttk.Combobox(
            signal_controls, textvariable=self.width_plot_component_var,
            state='readonly', width=5, values=['Bx', 'By']
        )
        width_signal_combo.pack(side=tk.LEFT, padx=(0, 12))

        ttk.Label(
            signal_controls,
            text='Default report sizing: Length = Bx, Width = Bx | Max Raw = Bx Raw'
        ).pack(side=tk.LEFT, padx=(6, 0))

        length_signal_combo.bind('<<ComboboxSelected>>', lambda e: self.update_selected_signal_plot())
        width_signal_combo.bind('<<ComboboxSelected>>', lambda e: self.update_selected_signal_plot())

        self.signal_canvas = FigureCanvasTkAgg(self.signal_fig, master=self.signal_host)
        self.signal_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._clear_selected_signal_plot('Click an ROI in the ROI List to display its signal.')
        from .defect_3d import build_embedded_3d
        build_embedded_3d(self, self.pipe_3d_host)

        # Always-available mouse navigation:
        # wheel = zoom around cursor, right-button drag = pan
        self._right_pan = None
        self.canvas.mpl_connect('scroll_event', self.on_mouse_wheel_zoom)
        self.canvas.mpl_connect('button_press_event', self.on_mouse_press)
        self.canvas.mpl_connect('motion_notify_event', self.on_mouse_motion)
        self.canvas.mpl_connect('button_release_event', self.on_mouse_release)

        controls = ttk.LabelFrame(right_frame, text='Defect ROI', padding=8)
        controls.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(controls, text='Add ROI (Drag Rectangle)', command=self.enable_crop).pack(fill=tk.X, pady=3)
        ttk.Button(controls, text='Reset View', command=self.reset_view).pack(fill=tk.X, pady=3)
        ttk.Label(controls, text='Mouse wheel: Zoom C-scan\nC-scan Y scrollbar: Rotate channel seam ONLY (no zoom) | X scrollbar: Odometer pan ONLY\nShift + mouse wheel: Scroll page Y\nRight-drag: Pan / Move',
                  justify=tk.LEFT).pack(fill=tk.X, pady=(5, 3))
        ttk.Button(controls, text='Change ROI Number / Order', command=self.change_selected_roi_number).pack(fill=tk.X, pady=3)
        ttk.Button(controls, text='Delete Selected ROI', command=self.delete_selected_roi).pack(fill=tk.X, pady=3)
        ttk.Button(controls, text='Clear All ROI', command=self.clear_rois).pack(fill=tk.X, pady=3)

        # Keep manual Length/Width method selectors permanently visible above the ROI table.
        # The older controls inside 'Selected ROI Properties' can fall below the visible
        # area on shorter screens because ROI List expands vertically.
        sizing_select_frame = ttk.LabelFrame(right_frame, text='Selected ROI - Length / Width Method', padding=6)
        sizing_select_frame.pack(fill=tk.X, padx=6, pady=(0, 6))

        ttk.Label(sizing_select_frame, text='Length:').grid(row=0, column=0, sticky='w', padx=(0, 4), pady=2)
        self.length_selected_combo_top = ttk.Combobox(
            sizing_select_frame, textvariable=self.length_selected_method_var, state='readonly', width=22,
            values=['Bx Length P-P','Bx Length Mountain','Bx Length @ Thr',
                    'Bz Length P-P','Bz Length Mountain','Bz Length @ Thr']
        )
        self.length_selected_combo_top.grid(row=0, column=1, sticky='ew', pady=2)

        ttk.Label(sizing_select_frame, text='Width:').grid(row=1, column=0, sticky='w', padx=(0, 4), pady=2)
        self.width_selected_combo_top = ttk.Combobox(
            sizing_select_frame, textvariable=self.width_selected_method_var, state='readonly', width=22,
            values=['Bx Width P-P','Bx Width Mountain','Bx Width @ Thr',
                    'By Width P-P','By Width Mountain','By Width @ Thr']
        )
        self.width_selected_combo_top.grid(row=1, column=1, sticky='ew', pady=2)

        ttk.Button(
            sizing_select_frame, text='Apply to Selected ROI',
            command=self.apply_selected_sizing_methods
        ).grid(row=0, column=2, padx=(6, 0), pady=2, sticky='ew')
        ttk.Button(
            sizing_select_frame, text='Apply to All ROI',
            command=self.apply_selected_sizing_methods_all
        ).grid(row=1, column=2, padx=(6, 0), pady=2, sticky='ew')

        sizing_select_frame.columnconfigure(1, weight=1)
        self.length_selected_combo_top.bind(
            '<<ComboboxSelected>>', lambda e: self.apply_selected_sizing_methods())
        self.width_selected_combo_top.bind(
            '<<ComboboxSelected>>', lambda e: self.apply_selected_sizing_methods())

        roi_frame = ttk.LabelFrame(right_frame, text='ROI List', padding=6)
        roi_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Eight dimension results are shown explicitly in the ROI table:
        # LENGTH: Bx normal mapping; Bz table method is swapped (Raw Thr <-> derivative P-P).
        # WIDTH : Bx and By both use Raw @Threshold and derivative P-P.
        cols = (
            'name', 'absmax', 'bx_max_odo', 'distance_from_defect1',
            'actual_length', 'actual_width', 'actual_depth',
            'best_length', 'best_width', 'velocity', 'thickness', 'ai_depth',
            'length_error', 'width_error', 'depth_error',
            # Advanced columns remain available from Table Columns...
            'bx_len_pp', 'bx_len_mountain', 'bx_len_thr', 'bz_len_pp', 'bz_len_mountain', 'bz_len_thr',
            'bx_wid_pp', 'bx_wid_mountain', 'bx_wid_thr', 'by_wid_pp', 'by_wid_mountain', 'by_wid_thr',
            'actual_depth_pct', 'actual_thickness',
            'depth', 'anomaly_class', 'ext_int', 'length_threshold', 'width_threshold'
        )
        self.table_columns = cols
        self.table_column_labels = {
            'name': 'ROI',
            'absmax': 'Max Raw',
            'bx_max_odo': 'Bx Max Odo (m)',
            'distance_from_defect1': 'Distance from Defect 1 (mm)',
            'bx_len_pp': 'Bx Length P-P',
            'bx_len_mountain': 'Bx Length Mountain',
            'bx_len_thr': 'Bx Length @ Thr',
            'bz_len_pp': 'Bz Length P-P',
            'bz_len_mountain': 'Bz Length Mountain',
            'bz_len_thr': 'Bz Length @ Thr',
            'bx_wid_pp': 'Bx Width P-P',
            'bx_wid_mountain': 'Bx Width Mountain',
            'bx_wid_thr': 'Bx Width @ Thr',
            'by_wid_pp': 'By Width P-P',
            'by_wid_mountain': 'By Width Mountain',
            'by_wid_thr': 'By Width @ Thr',
            'actual_length': 'Actual Length',
            'actual_width': 'Actual Width',
            'actual_depth': 'Actual Depth (mm)',
            'actual_depth_pct': 'Actual Depth (%)',
            'actual_thickness': 'Actual WT',
            'best_length': 'Length selected',
            'best_width': 'Width selected',
            'velocity': 'Velocity (m/s)',
            'thickness': 'Thickness (mm)',
            'length_error': 'Length Error',
            'width_error': 'Width Error',
            'depth_error': 'Depth Error',
            'depth': 'Depth (%/mm)',
            'ai_depth': 'AI Depth (mm / %WT)',
            'anomaly_class': 'Anomaly Dimension Class',
            'ext_int': 'Ext/Int',
            'length_threshold': 'Length Thr.',
            'width_threshold': 'Width Thr.',
        }
        # Compact default view matching the v44 appearance.
        # Actual/reference/error columns are still available from Table Columns...
        # but stay hidden by default to keep the right-side table uncluttered.
        # Default report-oriented table: actual values in ROI order, the selected
        # closest Length/Width, then only Length/Width/Depth errors.
        self.table_default_columns = (
            'name', 'absmax', 'bx_max_odo', 'distance_from_defect1',
            'actual_length', 'actual_width', 'actual_depth',
            'best_length', 'best_width', 'velocity', 'thickness', 'ai_depth',
            'length_error', 'width_error', 'depth_error'
        )
        self.table_column_vars = {
            col: tk.BooleanVar(value=(col in self.table_default_columns)) for col in cols
        }

        table_tools = ttk.Frame(roi_frame)
        table_tools.pack(side=tk.TOP, fill=tk.X, pady=(0, 5))
        ttk.Button(table_tools, text='Table Columns...', command=self.open_table_columns_dialog).pack(side=tk.LEFT)
        ttk.Button(table_tools, text='Default View', command=self.set_default_table_columns).pack(side=tk.LEFT, padx=4)
        ttk.Button(table_tools, text='Copy Table', command=self.copy_table_to_clipboard).pack(side=tk.LEFT, padx=4)

        self.tree = ttk.Treeview(roi_frame, columns=cols, show='headings', height=20)
        self.tree.heading('name', text='ROI')
        self.tree.heading('absmax', text='Max Raw')
        self.tree.heading('bx_max_odo', text='Bx Max Odo (m)')
        self.tree.heading('distance_from_defect1', text='Distance from Defect 1 (mm)')
        self.tree.heading('bx_len_pp', text='Bx Length P-P')
        self.tree.heading('bx_len_mountain', text='Bx Length Mountain')
        self.tree.heading('bx_len_thr', text='Bx Length @ Thr')
        self.tree.heading('bz_len_pp', text='Bz Length P-P')
        self.tree.heading('bz_len_mountain', text='Bz Length Mountain')
        self.tree.heading('bz_len_thr', text='Bz Length @ Thr')
        self.tree.heading('bx_wid_pp', text='Bx Width P-P')
        self.tree.heading('bx_wid_mountain', text='Bx Width Mountain')
        self.tree.heading('bx_wid_thr', text='Bx Width @ Thr')
        self.tree.heading('by_wid_pp', text='By Width P-P')
        self.tree.heading('by_wid_mountain', text='By Width Mountain')
        self.tree.heading('by_wid_thr', text='By Width @ Thr')
        self.tree.heading('actual_length', text='Actual Length')
        self.tree.heading('actual_width', text='Actual Width')
        self.tree.heading('actual_depth', text='Actual Depth (mm)')
        self.tree.heading('actual_depth_pct', text='Actual Depth (%)')
        self.tree.heading('actual_thickness', text='Actual WT')
        self.tree.heading('best_length', text='Length selected')
        self.tree.heading('best_width', text='Width selected')
        self.tree.heading('velocity', text='Velocity (m/s)')
        self.tree.heading('thickness', text='Thickness (mm)')
        self.tree.heading('length_error', text='Length Error')
        self.tree.heading('width_error', text='Width Error')
        self.tree.heading('depth_error', text='Depth Error')
        self.tree.heading('depth', text='Depth (%/mm)')
        self.tree.heading('ai_depth', text='AI Depth (mm / %WT)')
        self.tree.heading('anomaly_class', text='Anomaly Dimension Class')
        self.tree.heading('ext_int', text='Ext/Int')
        self.tree.heading('length_threshold', text='Length Thr.')
        self.tree.heading('width_threshold', text='Width Thr.')
        self.tree.column('name', width=50, anchor='center')
        self.tree.column('absmax', width=85, anchor='center')
        self.tree.column('bx_max_odo', width=105, anchor='center')
        self.tree.column('distance_from_defect1', width=155, anchor='center')
        for col in ('bx_len_pp','bx_len_mountain','bx_len_thr','bz_len_pp','bz_len_mountain','bz_len_thr',
                    'bx_wid_pp','bx_wid_mountain','bx_wid_thr','by_wid_pp','by_wid_mountain','by_wid_thr'):
            self.tree.column(col, width=105, anchor='center')
        for col in ('actual_length','actual_width','actual_depth','actual_depth_pct','actual_thickness'):
            self.tree.column(col, width=95, anchor='center')
        self.tree.column('best_length', width=180, anchor='center')
        self.tree.column('best_width', width=180, anchor='center')
        self.tree.column('velocity', width=90, anchor='center')
        self.tree.column('thickness', width=95, anchor='center')
        self.tree.column('length_error', width=135, anchor='center')
        self.tree.column('width_error', width=135, anchor='center')
        self.tree.column('depth_error', width=135, anchor='center')
        self.tree.column('depth', width=130, anchor='center')
        self.tree.column('ai_depth', width=130, anchor='center')
        self.tree.column('anomaly_class', width=150, anchor='center')
        self.tree.column('ext_int', width=65, anchor='center')
        self.tree.column('length_threshold', width=78, anchor='center')
        self.tree.column('width_threshold', width=78, anchor='center')
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Vertical scroll is wrapped so the colored Anomaly Dimension Class cells
        # stay aligned with their Treeview rows while scrolling.
        self._class_cell_labels = {}
        self.anomaly_class_cell_colors = {
            'Pin-hole': '#FFF4B8',
            'Pitting': '#FFD9B3',
            'Axial grooving': '#CFE8FF',
            'Circumferential grooving': '#E4D5FF',
            'Axial slotting': '#D7F5D0',
            'Circumferential slotting': '#CFF4F4',
            'General': '#FFB8B8',
            'Unclassified': '#E5E5E5',
            'Set WT': '#F4F4F4',
        }

        def _tree_yview(*args):
            self.tree.yview(*args)
            self._schedule_class_cell_overlays()

        scr = ttk.Scrollbar(roi_frame, orient=tk.VERTICAL, command=_tree_yview)
        scr.pack(side=tk.RIGHT, fill=tk.Y)

        def _tree_yscroll(first, last):
            scr.set(first, last)
            self._schedule_class_cell_overlays()

        self.tree.configure(yscrollcommand=_tree_yscroll)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.on_roi_selected())
        self.tree.bind('<Configure>', lambda e: self._schedule_class_cell_overlays(), add='+')
        self.tree.bind('<MouseWheel>', lambda e: self._schedule_class_cell_overlays(), add='+')
        self.tree.bind('<ButtonRelease-1>', lambda e: self._schedule_class_cell_overlays(), add='+')
        self.tree.bind('<KeyRelease>', lambda e: self._schedule_class_cell_overlays(), add='+')
        self.tree.bind('<Control-c>', self.copy_selected_table_rows, add='+')
        self.tree.bind('<Control-C>', self.copy_selected_table_rows, add='+')

        # Only the Anomaly Dimension Class CELL is colored. Other cells keep the
        # normal Treeview theme/background. Treeview itself cannot style one cell,
        # so a small Label is overlaid exactly on that visible cell.
        self.apply_table_column_visibility()

        # Global wall thickness: one value is used for every ROI.
        wt_frame = ttk.LabelFrame(right_frame, text='Global Wall Thickness', padding=8)
        wt_frame.pack(fill=tk.X, padx=6, pady=6)
        ttk.Label(wt_frame, text='Wall Thickness t (mm):').pack(side=tk.LEFT)
        wt_combo = ttk.Combobox(
            wt_frame, textvariable=self.wall_thickness_var, state='readonly', width=10,
            values=['12.7', '10.31']
        )
        wt_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(wt_frame, text='(used for all ROI)').pack(side=tk.LEFT, padx=(4, 0))
        wt_combo.bind('<<ComboboxSelected>>', self.on_global_wt_changed)

        ai_frame = ttk.LabelFrame(right_frame, text='Physics AI Depth Training / Prediction', padding=8)
        ai_frame.pack(fill=tk.X, padx=6, pady=6)
        ttk.Label(ai_frame, text='Training WT 12.70:').grid(row=0, column=0, sticky='w', pady=2)
        ttk.Entry(ai_frame, textvariable=self.ai_training_path_127_var, width=32).grid(row=0, column=1, padx=4, pady=2, sticky='ew')
        ttk.Button(ai_frame, text='Browse', command=lambda: self.browse_ai_training_file(12.70)).grid(row=0, column=2, padx=3, pady=2)

        ttk.Label(ai_frame, text='Training WT 10.31:').grid(row=1, column=0, sticky='w', pady=2)
        ttk.Entry(ai_frame, textvariable=self.ai_training_path_1031_var, width=32).grid(row=1, column=1, padx=4, pady=2, sticky='ew')
        ttk.Button(ai_frame, text='Browse', command=lambda: self.browse_ai_training_file(10.31)).grid(row=1, column=2, padx=3, pady=2)
        ttk.Button(ai_frame, text='Train Physics AI', command=self.train_ai_depth_model).grid(row=0, column=3, rowspan=2, padx=3, pady=2, sticky='ns')

        ttk.Label(ai_frame, text='Velocity (m/s):').grid(row=2, column=0, sticky='w', pady=2)
        ttk.Entry(ai_frame, textvariable=self.ai_velocity_var, width=10).grid(row=2, column=1, padx=4, pady=2, sticky='w')

        ttk.Label(ai_frame, text='AI Length:').grid(row=3, column=0, sticky='w', pady=2)
        ttk.Label(ai_frame, text='Length Selected').grid(row=3, column=1, padx=4, pady=2, sticky='w')

        ttk.Label(ai_frame, text='AI Width:').grid(row=4, column=0, sticky='w', pady=2)
        ttk.Label(ai_frame, text='Width Selected').grid(row=4, column=1, padx=4, pady=2, sticky='w')

        ttk.Button(ai_frame, text='Predict Selected', command=self.predict_ai_depth_selected).grid(row=4, column=2, padx=3, pady=2, sticky='ew')
        ttk.Button(ai_frame, text='Predict All ROI', command=self.predict_ai_depth_all).grid(row=3, column=2, padx=3, pady=2, sticky='ew')
        ttk.Label(ai_frame, textvariable=self.ai_status_var, wraplength=330, justify=tk.LEFT).grid(
            row=5, column=0, columnspan=4, sticky='w', pady=(4, 0)
        )
        ai_frame.columnconfigure(1, weight=1)

        property_frame = ttk.LabelFrame(right_frame, text='Selected ROI Properties', padding=8)
        property_frame.pack(fill=tk.X, padx=6, pady=6)
        ttk.Label(property_frame, text='Depth (%/mm):').grid(row=0, column=0, sticky='w')
        ttk.Entry(property_frame, textvariable=self.depth_var, width=12).grid(row=0, column=1, padx=5, pady=2, sticky='w')

        ttk.Label(property_frame, text='Anomaly Dimension Class:').grid(row=1, column=0, sticky='w')
        ttk.Label(property_frame, textvariable=self.anomaly_class_var, width=24).grid(row=1, column=1, padx=5, pady=2, sticky='w')

        ttk.Label(property_frame, text='Ext/Int:').grid(row=2, column=0, sticky='w')
        extint_combo = ttk.Combobox(property_frame, textvariable=self.ext_int_var, state='readonly', width=18,
                                    values=['External', 'Internal'])
        extint_combo.grid(row=2, column=1, padx=5, pady=2, sticky='w')

        ttk.Label(property_frame, text='Length selected:').grid(row=3, column=0, sticky='w')
        length_selected_combo = ttk.Combobox(
            property_frame, textvariable=self.length_selected_method_var, state='readonly', width=22,
            values=['Bx Length P-P','Bx Length Mountain','Bx Length @ Thr',
                    'Bz Length P-P','Bz Length Mountain','Bz Length @ Thr'])
        length_selected_combo.grid(row=3, column=1, padx=5, pady=2, sticky='w')

        ttk.Label(property_frame, text='Width selected:').grid(row=4, column=0, sticky='w')
        width_selected_combo = ttk.Combobox(
            property_frame, textvariable=self.width_selected_method_var, state='readonly', width=22,
            values=['Bx Width P-P','Bx Width Mountain','Bx Width @ Thr',
                    'By Width P-P','By Width Mountain','By Width @ Thr'])
        width_selected_combo.grid(row=4, column=1, padx=5, pady=2, sticky='w')

        ttk.Button(property_frame, text='Apply ROI Properties', command=self.apply_properties_to_selected).grid(row=0, column=2, rowspan=5, padx=5, pady=2)
        length_selected_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_selected_sizing_methods())
        width_selected_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_selected_sizing_methods())

        threshold_frame = ttk.LabelFrame(right_frame, text='Selected ROI Thresholds', padding=8)
        threshold_frame.pack(fill=tk.X, padx=6, pady=6)
        ttk.Label(threshold_frame, text='Length Threshold (%):').grid(row=0, column=0, sticky='w', pady=2)
        length_threshold_entry = ttk.Entry(threshold_frame, textvariable=self.length_threshold_var, width=10)
        length_threshold_entry.grid(row=0, column=1, padx=5, pady=2, sticky='w')
        ttk.Label(threshold_frame, text='Defects in ROI:').grid(row=1, column=0, sticky='w', pady=2)
        defect_count_spin = ttk.Spinbox(threshold_frame, from_=1, to=20, textvariable=self.roi_defect_count_var, width=8)
        defect_count_spin.grid(row=1, column=1, padx=5, pady=2, sticky='w')
        ttk.Label(threshold_frame, text='Width Threshold (%):').grid(row=2, column=0, sticky='w', pady=2)
        width_threshold_entry = ttk.Entry(threshold_frame, textvariable=self.width_threshold_var, width=10)
        width_threshold_entry.grid(row=2, column=1, padx=5, pady=2, sticky='w')
        length_threshold_entry.bind('<Return>', lambda e: self.apply_threshold_to_selected())
        defect_count_spin.bind('<Return>', lambda e: self.apply_threshold_to_selected())
        width_threshold_entry.bind('<Return>', lambda e: self.apply_threshold_to_selected())
        ttk.Button(threshold_frame, text='Apply / Recalculate', command=self.apply_threshold_to_selected).grid(
            row=0, column=2, rowspan=3, padx=6, pady=2, sticky='ns')

        export_frame = ttk.LabelFrame(right_frame, text='Export', padding=8)
        export_frame.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(export_frame, text='View Selected ROI Raw / Derivative',
                   command=self.view_selected_roi).pack(fill=tk.X, pady=3)
        ttk.Button(export_frame, text='Export Selected ROI CSV', command=self.export_selected_csv).pack(fill=tk.X, pady=3)
        ttk.Button(export_frame, text='Save C-scan Image', command=self.save_figure).pack(fill=tk.X, pady=3)
        ttk.Button(export_frame, text='Show 3D in Lower-Left Panel', command=self.view_3d_defect).pack(fill=tk.X, pady=3)

        status = ttk.Label(self.root, textvariable=self.status_var, anchor='w', relief=tk.SUNKEN)
        status.pack(side=tk.BOTTOM, fill=tk.X)


    def apply_table_column_visibility(self):
        """Show only the selected ROI table columns; data/calculations remain unchanged."""
        if not hasattr(self, 'tree') or not self.table_columns:
            return
        visible = [c for c in self.table_columns
                   if c in self.table_column_vars and self.table_column_vars[c].get()]
        # Tk supports an empty display list, but keeping ROI visible makes the table usable.
        if not visible:
            if 'name' in self.table_column_vars:
                self.table_column_vars['name'].set(True)
            visible = ['name']
        self.tree.configure(displaycolumns=tuple(visible))
        self._schedule_class_cell_overlays()


    def set_all_table_columns(self, show=True):
        for var in self.table_column_vars.values():
            var.set(bool(show))
        self.apply_table_column_visibility()


    def set_default_table_columns(self):
        defaults = set(self.table_default_columns)
        for col, var in self.table_column_vars.items():
            var.set(col in defaults)
        self.apply_table_column_visibility()


    def open_table_columns_dialog(self):
        """Open a non-destructive column chooser for the ROI table."""
        if self._table_columns_window is not None:
            try:
                if self._table_columns_window.winfo_exists():
                    self._table_columns_window.lift()
                    self._table_columns_window.focus_force()
                    return
            except Exception:
                pass

        win = tk.Toplevel(self.root)
        self._table_columns_window = win
        win.title('ROI Table Columns')
        win.geometry('390x610')
        win.transient(self.root)

        ttk.Label(
            win,
            text='Select the columns to show in the ROI table.\nHidden columns are still calculated and kept in memory.',
            justify=tk.LEFT
        ).pack(fill=tk.X, padx=10, pady=(10, 6))

        outer = ttk.Frame(win)
        outer.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        canvas = tk.Canvas(outer, highlightthickness=0)
        vbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=vbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)

        def update_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox('all'))
        def fit_inner(event):
            canvas.itemconfigure(inner_id, width=event.width)
        inner.bind('<Configure>', update_scrollregion)
        canvas.bind('<Configure>', fit_inner)

        for col in self.table_columns:
            ttk.Checkbutton(
                inner,
                text=self.table_column_labels.get(col, col),
                variable=self.table_column_vars[col],
                command=self.apply_table_column_visibility
            ).pack(anchor='w', fill=tk.X, padx=6, pady=2)

        actions = ttk.Frame(win)
        actions.pack(fill=tk.X, padx=10, pady=(6, 10))
        ttk.Button(actions, text='Select All', command=lambda: self.set_all_table_columns(True)).pack(side=tk.LEFT)
        ttk.Button(actions, text='Clear All', command=lambda: self.set_all_table_columns(False)).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text='Default View', command=self.set_default_table_columns).pack(side=tk.LEFT, padx=5)
        ttk.Button(actions, text='Close', command=win.destroy).pack(side=tk.RIGHT)

        def on_close():
            self._table_columns_window = None
            win.destroy()
        win.protocol('WM_DELETE_WINDOW', on_close)


    def _schedule_class_cell_overlays(self):
        """Refresh colored class cells after Tk finishes geometry/scroll updates."""
        if not hasattr(self, 'tree'):
            return
        try:
            if getattr(self, '_class_overlay_after_id', None):
                self.tree.after_cancel(self._class_overlay_after_id)
        except Exception:
            pass
        try:
            self._class_overlay_after_id = self.tree.after_idle(self._refresh_class_cell_overlays)
        except Exception:
            self._class_overlay_after_id = None


    def _refresh_class_cell_overlays(self):
        """Color only the visible Anomaly Dimension Class cells.

        ttk.Treeview tags color an entire row, not one cell. To keep every other
        column untouched, this method places a tk.Label exactly over the class
        cell of each visible ROI row. Labels are repositioned on scroll/resize.
        """
        self._class_overlay_after_id = None
        if not hasattr(self, 'tree'):
            return

        # Hide all existing overlays first; visible rows are placed again below.
        for lbl in getattr(self, '_class_cell_labels', {}).values():
            try:
                lbl.place_forget()
            except Exception:
                pass

        try:
            display = tuple(self.tree.cget('displaycolumns'))
        except Exception:
            display = tuple()

        # Tk may report '#all' when all columns are visible.
        if not display or display == ('#all',):
            display = tuple(self.table_columns)
        if 'anomaly_class' not in display:
            return

        display_index = display.index('anomaly_class') + 1  # Treeview #1 based index
        tree_col = f'#{display_index}'

        roi_by_id = {str(r.get('id')): r for r in self.rois}
        for iid in self.tree.get_children(''):
            roi = roi_by_id.get(str(iid))
            if roi is None:
                continue
            try:
                bbox = self.tree.bbox(iid, tree_col)
            except Exception:
                bbox = ()
            if not bbox:
                continue
            x, y, w, h = bbox
            cls = str(roi.get('anomaly_class', 'Set WT'))
            bg = self.anomaly_class_cell_colors.get(cls, '#E5E5E5')
            fg = '#666666' if cls == 'Set WT' else '#000000'

            lbl = self._class_cell_labels.get(str(iid))
            if lbl is None or not lbl.winfo_exists():
                lbl = tk.Label(
                    self.tree, bd=0, relief='flat', anchor='center',
                    font='TkDefaultFont', padx=1, pady=0
                )
                lbl.bind('<Button-1>', lambda e, item=str(iid): self._select_roi_from_class_cell(item))
                self._class_cell_labels[str(iid)] = lbl
            lbl.configure(text=cls, background=bg, foreground=fg)
            # Leave a 1-pixel inset so the Treeview grid/row boundaries remain visible.
            lbl.place(x=x + 1, y=y + 1, width=max(1, w - 2), height=max(1, h - 2))
            lbl.lift()


    def _select_roi_from_class_cell(self, iid):
        """Make the colored class cell behave like the Treeview row beneath it."""
        try:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                self.tree.see(iid)
                self.on_roi_selected()
                self._schedule_class_cell_overlays()
        except Exception:
            pass


