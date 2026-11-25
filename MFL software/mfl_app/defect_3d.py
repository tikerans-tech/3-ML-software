"""24-inch pipe eighth-section visualization for selected ROI (illustrative geometry)."""
import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

OD = 609.6
SAMPLE_LENGTH = 900.0
ANGLE = np.pi / 4

def _positive(value):
    try:
        value = float(value)
        return value if np.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None

def build_embedded_3d(app, host):
    controls = ttk.Frame(host, padding=4)
    controls.pack(fill=tk.X)
    ttk.Label(controls, text='24-inch OD | 1/8 section (45 deg) | 900 mm | Centered axial seam').pack(side=tk.LEFT, padx=3)
    wt_var = tk.StringVar(value='9.53')
    ttk.Label(controls, text='WT (mm):').pack(side=tk.LEFT, padx=(15, 3))
    ttk.Combobox(controls, textvariable=wt_var, values=['9.53', '17.48'], width=8).pack(side=tk.LEFT)
    side_var = tk.StringVar(value='External')
    ttk.Combobox(controls, textvariable=side_var, values=['External', 'Internal'], state='readonly', width=10).pack(side=tk.LEFT, padx=8)
    mode_var = tk.StringVar(value='Predicted')
    ttk.Combobox(controls, textvariable=mode_var, values=['Predicted', 'Actual'], state='readonly', width=12).pack(side=tk.LEFT)
    fig = Figure(figsize=(12, 6.5), dpi=100)
    ax = fig.add_subplot(121, projection='3d')
    zoom = fig.add_subplot(122, projection='3d')
    canvas = FigureCanvasTkAgg(fig, master=host)
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    toolbar = NavigationToolbar2Tk(canvas, host, pack_toolbar=False)
    toolbar.update()
    toolbar.pack(side=tk.BOTTOM, fill=tk.X)
    # Compact, readable pipe/defect information below the 3D graph.
    details = ttk.LabelFrame(host, text='Pipe & Defect Details', padding=(8, 5))
    details.pack(fill=tk.X, padx=4, pady=(2, 4))
    pipe_info = ttk.Label(details, justify=tk.LEFT, anchor='w',
        text='PIPE  |  OD: 609.6 mm (24 in)  |  Section: 1/8 (45 deg)  |  Length: 900 mm  |  Seam: Axial, centered')
    pipe_info.pack(fill=tk.X)
    defect_info = ttk.Label(details, justify=tk.LEFT, anchor='w',
        text='DEFECT  |  Select an ROI to show its dimensions.')
    defect_info.pack(fill=tk.X, pady=(3, 0))
    info = ttk.Label(host, text='', padding=4, wraplength=850)
    info.pack(fill=tk.X)

    def draw():
        roi = app.get_selected_roi() if hasattr(app, 'tree') else None
        pipe_info.config(text=f'PIPE  |  OD: 609.6 mm (24 in)  |  Section: 1/8 (45 deg)  |  Length: 900 mm  |  WT: {wt_var.get()} mm  |  Seam: Axial, centered')
        if roi is None:
            ax.clear(); zoom.clear()
            defect_info.config(text='DEFECT  |  Select an ROI to show its dimensions.')
            info.config(text='Select an ROI to display the 3D defect.')
            canvas.draw_idle()
            return
        try:
            wt = float(wt_var.get())
            if not (0 < wt < OD / 2):
                raise ValueError('Wall thickness must be between 0 and 304.8 mm')
        except ValueError as exc:
            messagebox.showerror('Wall thickness', str(exc))
            return
        actual = mode_var.get() == 'Actual'
        if actual:
            length = _positive(roi.get('actual_length_mm'))
            width = _positive(roi.get('actual_width_mm'))
            depth = _positive(roi.get('actual_depth_mm'))
        else:
            length = _positive(roi.get('best_length_mm')) or _positive(roi.get('length_selected_mm'))
            width = _positive(roi.get('best_width_mm')) or _positive(roi.get('width_selected_mm'))
            depth = _positive(roi.get('ai_depth_mm'))
        if length is None or width is None or depth is None:
            defect_info.config(text=f'DEFECT  |  ROI selected  |  {mode_var.get()}  |  Dimensions not available')
            info.config(text='Selected mode has missing Length, Width or Depth values. Train/predict AI or select Actual (if available).')
            ax.clear(); zoom.clear(); canvas.draw_idle()
            return
        if depth >= wt:
            info.config(text=f'Warning: Depth {depth:.3f} mm exceeds WT {wt:.2f} mm; display clipped to wall thickness.')
        depth = min(depth, wt * 0.99)
        length = min(length, SAMPLE_LENGTH)
        R = OD / 2
        ri = R - wt
        t = np.linspace(-ANGLE / 2, ANGLE / 2, 55)
        x = np.linspace(-SAMPLE_LENGTH / 2, SAMPLE_LENGTH / 2, 65)
        X, T = np.meshgrid(x, t)
        def surf(axis, radius, color, alpha):
            axis.plot_surface(X, radius * np.sin(T), radius * np.cos(T), color=color, alpha=alpha, linewidth=0, shade=True)
        ax.clear(); zoom.clear()
        surf(ax, R, '#a6b7c8', 0.68)
        surf(ax, ri, '#8498ab', 0.33)
        for angle in [-ANGLE/2, ANGLE/2]:
            for radius in [ri, R]:
                ax.plot(x, np.full_like(x, radius*np.sin(angle)), np.full_like(x, radius*np.cos(angle)), color='#52657b', lw=0.8)
            for xx in [-SAMPLE_LENGTH/2, SAMPLE_LENGTH/2]:
                rs = np.linspace(ri, R, 8)
                ax.plot(np.full_like(rs, xx), rs*np.sin(angle), rs*np.cos(angle), color='#52657b', lw=0.8)
        # Centered axial seam and defect indication on actual pipe curvature.
        ax.plot(x, np.zeros_like(x), np.full_like(x, R+0.7), color='#c17b45', lw=2, label='Axial seam weld')
        flaw_r = R if side_var.get() == 'External' else ri
        xx = np.linspace(-length/2, length/2, 20)
        tt = np.linspace(-width/(2*flaw_r), width/(2*flaw_r), 9)
        XX, TT = np.meshgrid(xx, tt)
        ax.plot_surface(XX, (flaw_r + (1 if side_var.get() == 'External' else -1)*1.5)*np.sin(TT), (flaw_r + (1 if side_var.get() == 'External' else -1)*1.5)*np.cos(TT), color='#dc4c3e', alpha=0.98)
        ax.set_title('Full 24-inch Pipe / 1/8 Section')
        ax.set_xlabel('Axial (mm)'); ax.set_ylabel('Circumferential (mm)'); ax.set_zlabel('Radial (mm)')
        ax.set_box_aspect((900, 250, 140))
        ax.view_init(elev=26, azim=-64)
        # Local tangent-plane cutaway for sub-mm flaws. Vertical exaggeration is display-only.
        scale = max(length, width, 1.0)
        lx = max(length*1.8, 2.0)
        wy = max(width*3.0, 0.2)
        # Normalize depth visually to make microscopic flaws observable.
        z_top = 0.0
        z_bottom = -wt
        zx, zy = np.meshgrid(np.linspace(-lx/2,lx/2,2),np.linspace(-wy/2,wy/2,2))
        zoom.plot_surface(zx, zy, np.zeros_like(zx), color='#a8b8c8', alpha=.48)
        zoom.plot_surface(zx, zy, np.full_like(zx, -wt), color='#75879b', alpha=.12)
        a = np.array([-length/2,length/2]); b=np.array([-width/2,width/2]); d=-depth
        # Slot bottom and four vertical faces; local flat approximation of curved pipe.
        sx, sy = np.meshgrid(a,b)
        zoom.plot_surface(sx,sy,np.full_like(sx,d),color='#b85b45',alpha=.98)
        for yv in b:
            vx,vz=np.meshgrid(a,[d,0])
            zoom.plot_surface(vx,np.full_like(vx,yv),vz,color='#d77a59',alpha=.95)
        for xv in a:
            vy,vz=np.meshgrid(b,[d,0])
            zoom.plot_surface(np.full_like(vy,xv),vy,vz,color='#bd684b',alpha=.95)
        zoom.set_xlim(-lx/2,lx/2);zoom.set_ylim(-wy/2,wy/2)
        zoom.set_zlim(-max(wt,depth)*1.1, max(depth*.3,.05))
        zoom.set_box_aspect((1.7,1.0,.75))
        zoom.set_title('Defect Detail (local tangent-plane cutaway)')
        zoom.set_xlabel('Length (mm)');zoom.set_ylabel('Width (mm)');zoom.set_zlabel('Depth (mm)')
        zoom.view_init(elev=28,azim=-55)
        fig.tight_layout(pad=2)
        canvas.draw_idle()
        defect_info.config(text=f'DEFECT  |  {mode_var.get()}  |  {side_var.get()}  |  Rectangular slot  |  Length: {length:.4g} mm  |  Width: {width:.4g} mm  |  Depth: {depth:.4g} mm ({depth / wt * 100:.1f}% WT)')
        info.config(text='Schematic defect on the axial seam weld. Microscopic flaws are visually enlarged; actual topology cannot be recovered from dimensions alone.')
    ttk.Button(controls, text='Update 3D', command=draw).pack(side=tk.LEFT, padx=8)
    app._refresh_embedded_3d = draw
    # Do not draw here: the ROI Treeview is created later in _build_ui.
    # switch_lower_view() and ROI selection trigger drawing once ready.
    return canvas
