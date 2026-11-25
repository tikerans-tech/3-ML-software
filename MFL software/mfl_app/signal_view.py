from .common import *


class SignalViewMixin:
    def _clear_selected_signal_plot(self, message='Select an ROI to display signal.'):
        """Clear the embedded length/width signal viewer."""
        if not hasattr(self, 'signal_ax_raw'):
            return
        axes = [self.signal_ax_raw, self.signal_ax_deriv,
                self.signal_ax_width_raw, self.signal_ax_width_deriv]
        for ax in axes:
            ax.clear()
            ax.grid(True, alpha=0.25)
        self.signal_ax_raw.set_ylabel('Raw')
        self.signal_ax_deriv.set_ylabel('dSignal/dx')
        self.signal_ax_deriv.set_xlabel('Distance inside ROI (mm)')
        self.signal_ax_width_raw.set_ylabel('Raw')
        self.signal_ax_width_deriv.set_ylabel('dB/dChannel')
        self.signal_ax_width_deriv.set_xlabel('Width across channels (mm)')
        self.signal_ax_raw.text(0.5, 0.5, message, transform=self.signal_ax_raw.transAxes,
                                ha='center', va='center')
        if hasattr(self, 'signal_canvas'):
            self.signal_canvas.draw_idle()


    def update_selected_signal_plot(self, roi=None):
        if (hasattr(self, 'lower_view_var') and
                self.lower_view_var.get() == '3D Pipe Defect' and
                hasattr(self, '_refresh_embedded_3d')):
            self._refresh_embedded_3d()
        """Display selectable Length and Width component graphs for the ROI."""
        if roi is None:
            roi = self.get_selected_roi()
        if roi is None:
            self._clear_selected_signal_plot()
            return

        ds = next((d for d in self.datasets if d.path == roi['file_path']), None)
        if ds is None:
            self._clear_selected_signal_plot('Dataset for this ROI is not available.')
            return

        # Recalculate all four component analyses so thresholds and ROI bounds are current.
        self.calculate_peak_length(roi)
        self.calculate_anomaly_dimension_class(roi)
        self.refresh_roi_tree_item(roi)

        length_axis = self._component_name_to_axis(self.length_plot_component_var.get())
        width_axis = self._component_name_to_axis(self.width_plot_component_var.get())
        L = roi.get('length_analysis', {}).get(length_axis, {})
        W = roi.get('width_analysis', {}).get(width_axis, {})
        if not L:
            self._clear_selected_signal_plot(f'No {self.length_plot_component_var.get()} data for Length.')
            return
        if not W:
            self._clear_selected_signal_plot(f'No {self.width_plot_component_var.get()} data for Width.')
            return

        for ax in (self.signal_ax_raw, self.signal_ax_deriv,
                   self.signal_ax_width_raw, self.signal_ax_width_deriv):
            ax.clear()
            ax.grid(True, alpha=0.25)

        # ---------------- LENGTH: Bx/Bz versus x ----------------
        xr = np.asarray(L.get('x_raw', []), dtype=float)
        yr = np.asarray(L.get('raw', []), dtype=float)
        xd = np.asarray(L.get('x_deriv', []), dtype=float)
        yd = np.asarray(L.get('deriv', []), dtype=float)
        x0 = float(xr[0]) if xr.size else float(roi['x1'])
        xr_mm = (xr - x0) * 1000.0 if xr.size else np.asarray([])
        xd_mm = (xd - x0) * 1000.0 if xd.size else np.asarray([])
        lcomp = self.length_plot_component_var.get()
        lthr = float(L.get('threshold_percent', roi.get('length_threshold', 50.0)))
        length_swapped = (lcomp == 'Bz')

        # Raw length profile is always plotted. The CALCULATION METHOD changes by component:
        # Bx: Raw=@Threshold, dBx/dx=P-P
        # Bz: Raw=P-P,       dBz/dx=@Threshold   <-- true method swap
        if xr_mm.size and yr.size == xr_mm.size:
            self.signal_ax_raw.plot(xr_mm, yr, linewidth=1.25)
            self.signal_ax_raw.set_ylabel(f'{lcomp} raw')

            if length_swapped:
                # Bz RAW uses signed MAX/MIN -> P-P.
                px1, px2 = L.get('deriv_max_x', np.nan), L.get('deriv_min_x', np.nan)
                pv1, pv2 = L.get('deriv_max_value', np.nan), L.get('deriv_min_value', np.nan)
                # In swapped Bz analysis these fields intentionally hold RAW extrema.
                if np.isfinite(px1) and np.isfinite(pv1):
                    a=(float(px1)-x0)*1000.0
                    self.signal_ax_raw.plot(a,pv1,marker='^',markersize=7)
                    self.signal_ax_raw.axvline(a,linestyle='--',linewidth=1.0)
                    self.signal_ax_raw.annotate('RAW MAX',(a,pv1),xytext=(5,7),textcoords='offset points',fontsize=8)
                if np.isfinite(px2) and np.isfinite(pv2):
                    b=(float(px2)-x0)*1000.0
                    self.signal_ax_raw.plot(b,pv2,marker='v',markersize=7)
                    self.signal_ax_raw.axvline(b,linestyle='--',linewidth=1.0)
                    self.signal_ax_raw.annotate('RAW MIN',(b,pv2),xytext=(5,-12),textcoords='offset points',fontsize=8)
                if np.isfinite(px1) and np.isfinite(px2) and np.isfinite(L.get('pp_x2_mm',np.nan)):
                    a,b=sorted(((float(px1)-x0)*1000.0,(float(px2)-x0)*1000.0))
                    lo,hi=self.signal_ax_raw.get_ylim(); yy=hi-0.08*(hi-lo)
                    self.signal_ax_raw.annotate('',xy=(a,yy),xytext=(b,yy),arrowprops=dict(arrowstyle='<->',linewidth=1.2))
                    self.signal_ax_raw.text((a+b)/2.0,yy,f'RAW P-P = {L.get("pp_x2_mm"):.2f} mm',ha='center',va='bottom',fontsize=8)
                self.signal_ax_raw.text(0.01,0.98,
                    f'Bz RAW method = signed MAX/MIN -> P-P\n'
                    f'Length = |x(MAX)-x(MIN)| = {L.get("pp_x2_mm", np.nan):.2f} mm',
                    transform=self.signal_ax_raw.transAxes,ha='left',va='top',fontsize=7,
                    bbox=dict(boxstyle='round,pad=0.3',alpha=0.15))
            else:
                # Bx RAW uses percentage threshold method.
                px = L.get('max_raw_x', np.nan); py = L.get('max_raw', np.nan)
                if np.isfinite(px) and np.isfinite(py):
                    pxm=(float(px)-x0)*1000.0
                    self.signal_ax_raw.plot(pxm,py,marker='o',markersize=6)
                    self.signal_ax_raw.annotate(f'MAX {lcomp}={py:.4g}\nCh {L.get("channel", "-")}',xy=(pxm,py),xytext=(5,8),textcoords='offset points',fontsize=8)
                lm_x,rm_x=L.get('left_min_x',np.nan),L.get('right_min_x',np.nan)
                lm_v,rm_v=L.get('left_min_value',np.nan),L.get('right_min_value',np.nan)
                if np.isfinite(lm_x) and np.isfinite(lm_v):
                    a=(float(lm_x)-x0)*1000.0; self.signal_ax_raw.plot(a,lm_v,marker='v',markersize=6); self.signal_ax_raw.annotate('MIN L',(a,lm_v),xytext=(4,-12),textcoords='offset points',fontsize=8)
                if np.isfinite(rm_x) and np.isfinite(rm_v):
                    a=(float(rm_x)-x0)*1000.0; self.signal_ax_raw.plot(a,rm_v,marker='v',markersize=6); self.signal_ax_raw.annotate('MIN R',(a,rm_v),xytext=(4,-12),textcoords='offset points',fontsize=8)
                lx,rx=L.get('threshold_left_x',np.nan),L.get('threshold_right_x',np.nan)
                ll,rl=L.get('threshold_left_level',np.nan),L.get('threshold_right_level',np.nan)
                if np.isfinite(lx) and np.isfinite(rx):
                    lxm,rxm=(float(lx)-x0)*1000.0,(float(rx)-x0)*1000.0
                    self.signal_ax_raw.axvline(lxm,linestyle=':',linewidth=1.0); self.signal_ax_raw.axvline(rxm,linestyle=':',linewidth=1.0)
                    peakxm=(float(L.get('max_raw_x',lx))-x0)*1000.0
                    if np.isfinite(ll): self.signal_ax_raw.hlines(ll,lxm,peakxm,linestyles=':',linewidth=1.2)
                    if np.isfinite(rl): self.signal_ax_raw.hlines(rl,peakxm,rxm,linestyles=':',linewidth=1.2)
                    if np.isfinite(L.get('threshold_mm',np.nan)):
                        span=max(float(np.nanmax(yr)-np.nanmin(yr)),1e-12); yy=float(np.nanmax(yr))+0.08*span
                        self.signal_ax_raw.annotate('',xy=(lxm,yy),xytext=(rxm,yy),arrowprops=dict(arrowstyle='<->',linewidth=1.2))
                        self.signal_ax_raw.text((lxm+rxm)/2.0,yy,f'Length @ {lthr:.0f}% = {L.get("threshold_mm"):.2f} mm',ha='center',va='bottom',fontsize=8)
                self.signal_ax_raw.text(0.01,0.98,
                    f'Bx RAW method = @Threshold; T={lthr:.0f}%\nLength = x_R - x_L = {L.get("threshold_mm",np.nan):.2f} mm',
                    transform=self.signal_ax_raw.transAxes,ha='left',va='top',fontsize=7,bbox=dict(boxstyle='round,pad=0.3',alpha=0.15))

        if xd_mm.size and yd.size == xd_mm.size:
            self.signal_ax_deriv.plot(xd_mm,yd,linewidth=1.25)
            self.signal_ax_deriv.axhline(0.0,linewidth=0.8)
            self.signal_ax_deriv.set_ylabel(f'd{lcomp}/dx')
            self.signal_ax_deriv.set_xlabel('Distance inside ROI (mm)')

            if length_swapped:
                # dBz/dx uses @Threshold, not P-P.
                lx,rx=L.get('threshold_left_x',np.nan),L.get('threshold_right_x',np.nan)
                ll,rl=L.get('threshold_left_level',np.nan),L.get('threshold_right_level',np.nan)
                pi=L.get('threshold_peak_idx')
                if isinstance(pi,(int,np.integer)) and 0<=pi<yd.size:
                    self.signal_ax_deriv.plot(xd_mm[pi],yd[pi],marker='o',markersize=6)
                    self.signal_ax_deriv.annotate('DERIV MAX',(xd_mm[pi],yd[pi]),xytext=(5,7),textcoords='offset points',fontsize=8)
                    peakx=xd_mm[pi]
                else:
                    peakx=np.nan
                if np.isfinite(lx) and np.isfinite(rx):
                    lxm,rxm=(float(lx)-x0)*1000.0,(float(rx)-x0)*1000.0
                    self.signal_ax_deriv.axvline(lxm,linestyle=':',linewidth=1.0); self.signal_ax_deriv.axvline(rxm,linestyle=':',linewidth=1.0)
                    if np.isfinite(ll) and np.isfinite(peakx): self.signal_ax_deriv.hlines(ll,lxm,peakx,linestyles=':',linewidth=1.2)
                    if np.isfinite(rl) and np.isfinite(peakx): self.signal_ax_deriv.hlines(rl,peakx,rxm,linestyles=':',linewidth=1.2)
                    if np.isfinite(L.get('threshold_mm',np.nan)):
                        lo,hi=self.signal_ax_deriv.get_ylim(); yy=hi-0.08*(hi-lo)
                        self.signal_ax_deriv.annotate('',xy=(lxm,yy),xytext=(rxm,yy),arrowprops=dict(arrowstyle='<->',linewidth=1.2))
                        self.signal_ax_deriv.text((lxm+rxm)/2.0,yy,f'dBz/dx @ {lthr:.0f}% = {L.get("threshold_mm"):.2f} mm',ha='center',va='bottom',fontsize=8)
                self.signal_ax_deriv.text(0.01,0.98,
                    f'dBz/dx method = @Threshold; T={lthr:.0f}%\nLength = x_R - x_L = {L.get("threshold_mm",np.nan):.2f} mm',
                    transform=self.signal_ax_deriv.transAxes,ha='left',va='top',fontsize=7,bbox=dict(boxstyle='round,pad=0.3',alpha=0.15))
            else:
                # dBx/dx uses signed MAX/MIN -> P-P.
                dx1,dx2=L.get('deriv_max_x',np.nan),L.get('deriv_min_x',np.nan); dv1,dv2=L.get('deriv_max_value',np.nan),L.get('deriv_min_value',np.nan)
                if np.isfinite(dx1) and np.isfinite(dv1):
                    a=(float(dx1)-x0)*1000.0; self.signal_ax_deriv.plot(a,dv1,marker='^',markersize=7); self.signal_ax_deriv.axvline(a,linestyle='--',linewidth=1.0); self.signal_ax_deriv.annotate('MAX',(a,dv1),xytext=(5,7),textcoords='offset points',fontsize=8)
                if np.isfinite(dx2) and np.isfinite(dv2):
                    b=(float(dx2)-x0)*1000.0; self.signal_ax_deriv.plot(b,dv2,marker='v',markersize=7); self.signal_ax_deriv.axvline(b,linestyle='--',linewidth=1.0); self.signal_ax_deriv.annotate('MIN',(b,dv2),xytext=(5,-12),textcoords='offset points',fontsize=8)
                if np.isfinite(dx1) and np.isfinite(dx2) and np.isfinite(L.get('pp_x2_mm',np.nan)):
                    a,b=sorted(((float(dx1)-x0)*1000.0,(float(dx2)-x0)*1000.0)); lo,hi=self.signal_ax_deriv.get_ylim(); yy=hi-0.08*(hi-lo)
                    self.signal_ax_deriv.annotate('',xy=(a,yy),xytext=(b,yy),arrowprops=dict(arrowstyle='<->',linewidth=1.2)); self.signal_ax_deriv.text((a+b)/2.0,yy,f'P-P = {L.get("pp_x2_mm"):.2f} mm',ha='center',va='bottom',fontsize=8)

        # Multi-defect overlay for Bx RAW. If one ROI contains consecutive
        # defects, show each peak and its own threshold length independently.
        multi = L.get('multi_defects', []) if lcomp == 'Bx' else []
        if len(multi) >= 2 and xr_mm.size:
            for dct in multi:
                no = int(dct.get('defect_no', 0))
                px = dct.get('peak_x', np.nan); pv = dct.get('peak_value', np.nan)
                lx = dct.get('threshold_left_x', np.nan); rx = dct.get('threshold_right_x', np.nan)
                if np.isfinite(px) and np.isfinite(pv):
                    pm = (float(px)-x0)*1000.0
                    self.signal_ax_raw.plot(pm, pv, marker='o', markersize=7)
                    self.signal_ax_raw.annotate(f'Defect {no}', (pm,pv), xytext=(4,10),
                                                textcoords='offset points', fontsize=8, fontweight='bold')
                if np.isfinite(lx) and np.isfinite(rx):
                    lm=(float(lx)-x0)*1000.0; rm=(float(rx)-x0)*1000.0
                    self.signal_ax_raw.axvline(lm, linestyle=':', linewidth=1.0)
                    self.signal_ax_raw.axvline(rm, linestyle=':', linewidth=1.0)
                    length=dct.get('threshold_mm', np.nan)
                    base=dct.get('threshold_base_mm', np.nan)
                    if np.isfinite(length):
                        label = (f'D{no}: {base:.2f} x 2 = {length:.2f} mm'
                                 if np.isfinite(base) and float(dct.get('length_multiplier',1.0)) > 1.0
                                 else f'D{no}: {length:.2f} mm')
                        self.signal_ax_raw.text((lm+rm)/2.0, 0.04 + 0.055*((no-1)%3),
                            label, transform=self.signal_ax_raw.get_xaxis_transform(),
                            ha='center', va='bottom', fontsize=8,
                            bbox=dict(boxstyle='round,pad=0.2', alpha=0.12))
            summary = ' | '.join(
                f"D{int(d.get('defect_no',0))}={d.get('threshold_mm',np.nan):.2f} mm"
                for d in multi if np.isfinite(d.get('threshold_mm',np.nan)))
            self.signal_ax_raw.text(0.99,0.98,
                f'{len(multi)} defects detected in this ROI | Threshold = {lthr:.0f}% | Length = measured span x 2\n{summary}',
                transform=self.signal_ax_raw.transAxes, ha='right', va='top', fontsize=8,
                bbox=dict(boxstyle='round,pad=0.35', alpha=0.18))

        if lcomp == 'Bx' and len(L.get('multi_defects', [])) >= 2:
            self.signal_ax_raw.set_title(
                f'LENGTH RAW: {lcomp}/x | {len(L.get("multi_defects", []))} DEFECTS IN ROI | @{lthr:.0f}% then x2', fontsize=9)
        else:
            self.signal_ax_raw.set_title(f'LENGTH RAW: {lcomp}/x | Method: {"P-P" if length_swapped else "@Threshold"}',fontsize=9)
        self.signal_ax_deriv.set_title(f'LENGTH DERIVATIVE: d{lcomp}/dx | Method: {"@Threshold" if length_swapped else "P-P"}',fontsize=9)

        # ---------------- WIDTH: Bx/By versus channel ----------------
        wpos=np.asarray(W.get('pos_mm',[]),dtype=float); wraw=np.asarray(W.get('raw',[]),dtype=float); wdy=np.asarray(W.get('deriv',[]),dtype=float)
        wcomp=self.width_plot_component_var.get(); wthr_pct=float(W.get('threshold_percent',roi.get('width_threshold',50.0)))
        width_swapped=False  # Bx and By: RAW=@Threshold, derivative=P-P

        if wpos.size and wraw.size==wpos.size:
            self.signal_ax_width_raw.plot(wpos,wraw,marker='o',linewidth=1.25,markersize=3)
            self.signal_ax_width_raw.set_ylabel(f'{wcomp} raw')
            if width_swapped:
                # By RAW uses signed MAX/MIN -> P-P.
                ap,bp=W.get('deriv_max_pos_mm',np.nan),W.get('deriv_min_pos_mm',np.nan); av,bv=W.get('deriv_max_value',np.nan),W.get('deriv_min_value',np.nan)
                # In swapped By analysis these fields intentionally hold RAW extrema.
                if np.isfinite(ap) and np.isfinite(av): self.signal_ax_width_raw.plot(ap,av,marker='^',markersize=7); self.signal_ax_width_raw.axvline(ap,linestyle='--',linewidth=1.0); self.signal_ax_width_raw.annotate('RAW MAX',(ap,av),xytext=(5,7),textcoords='offset points',fontsize=8)
                if np.isfinite(bp) and np.isfinite(bv): self.signal_ax_width_raw.plot(bp,bv,marker='v',markersize=7); self.signal_ax_width_raw.axvline(bp,linestyle='--',linewidth=1.0); self.signal_ax_width_raw.annotate('RAW MIN',(bp,bv),xytext=(5,-12),textcoords='offset points',fontsize=8)
                if np.isfinite(ap) and np.isfinite(bp) and np.isfinite(W.get('pp_x2_mm',np.nan)):
                    a,b=sorted((float(ap),float(bp))); lo,hi=self.signal_ax_width_raw.get_ylim(); yy=hi-0.08*(hi-lo)
                    self.signal_ax_width_raw.annotate('',xy=(a,yy),xytext=(b,yy),arrowprops=dict(arrowstyle='<->',linewidth=1.2)); self.signal_ax_width_raw.text((a+b)/2.0,yy,f'RAW P-P = {W.get("pp_x2_mm"):.2f} mm',ha='center',va='bottom',fontsize=8)
                self.signal_ax_width_raw.text(0.01,0.98,
                    f'By RAW method = signed MAX/MIN -> P-P\nWidth = |pos(MAX)-pos(MIN)| = {W.get("pp_x2_mm",np.nan):.2f} mm',
                    transform=self.signal_ax_width_raw.transAxes,ha='left',va='top',fontsize=7,bbox=dict(boxstyle='round,pad=0.3',alpha=0.15))
            else:
                # Bx RAW width uses threshold.
                pi=W.get('peak_idx')
                if isinstance(pi,(int,np.integer)) and 0<=pi<wpos.size:
                    self.signal_ax_width_raw.plot(wpos[pi],wraw[pi],marker='o',markersize=6); self.signal_ax_width_raw.annotate(f'MAX Ch {W.get("channel","-")}',(wpos[pi],wraw[pi]),xytext=(5,7),textcoords='offset points',fontsize=8)
                lp,rp=W.get('threshold_left_pos_mm',np.nan),W.get('threshold_right_pos_mm',np.nan); ll,rl=W.get('threshold_left_level',np.nan),W.get('threshold_right_level',np.nan)
                if np.isfinite(lp) and np.isfinite(rp):
                    self.signal_ax_width_raw.axvline(lp,linestyle=':',linewidth=1.0); self.signal_ax_width_raw.axvline(rp,linestyle=':',linewidth=1.0)
                    peakp=float(wpos[pi]) if isinstance(pi,(int,np.integer)) and 0<=pi<wpos.size else np.nan
                    if np.isfinite(ll) and np.isfinite(peakp): self.signal_ax_width_raw.hlines(ll,lp,peakp,linestyles=':',linewidth=1.2)
                    if np.isfinite(rl) and np.isfinite(peakp): self.signal_ax_width_raw.hlines(rl,peakp,rp,linestyles=':',linewidth=1.2)
                    if np.isfinite(W.get('threshold_mm',np.nan)):
                        span=max(float(np.nanmax(wraw)-np.nanmin(wraw)),1e-12); yy=float(np.nanmax(wraw))+0.08*span
                        self.signal_ax_width_raw.annotate('',xy=(lp,yy),xytext=(rp,yy),arrowprops=dict(arrowstyle='<->',linewidth=1.2)); self.signal_ax_width_raw.text((lp+rp)/2.0,yy,f'Width @ {wthr_pct:.0f}% = {W.get("threshold_mm"):.2f} mm',ha='center',va='bottom',fontsize=8)
                self.signal_ax_width_raw.text(0.01,0.98,f'Bx RAW method = @Threshold; T={wthr_pct:.0f}%\nWidth = pos_R-pos_L = {W.get("threshold_mm",np.nan):.2f} mm',transform=self.signal_ax_width_raw.transAxes,ha='left',va='top',fontsize=7,bbox=dict(boxstyle='round,pad=0.3',alpha=0.15))

        if wpos.size and wdy.size==wpos.size:
            self.signal_ax_width_deriv.plot(wpos,wdy,marker='o',linewidth=1.25,markersize=3)
            self.signal_ax_width_deriv.axhline(0.0,linewidth=0.8)
            self.signal_ax_width_deriv.set_ylabel(f'd{wcomp}/dChannel'); self.signal_ax_width_deriv.set_xlabel('Width across channels (mm)')
            if width_swapped:
                # dBy/dChannel uses @Threshold.
                lp,rp=W.get('threshold_left_pos_mm',np.nan),W.get('threshold_right_pos_mm',np.nan); ll,rl=W.get('threshold_left_level',np.nan),W.get('threshold_right_level',np.nan); pi=W.get('threshold_peak_idx')
                if isinstance(pi,(int,np.integer)) and 0<=pi<wpos.size:
                    self.signal_ax_width_deriv.plot(wpos[pi],wdy[pi],marker='o',markersize=6); self.signal_ax_width_deriv.annotate('DERIV MAX',(wpos[pi],wdy[pi]),xytext=(5,7),textcoords='offset points',fontsize=8); peakp=wpos[pi]
                else: peakp=np.nan
                if np.isfinite(lp) and np.isfinite(rp):
                    self.signal_ax_width_deriv.axvline(lp,linestyle=':',linewidth=1.0); self.signal_ax_width_deriv.axvline(rp,linestyle=':',linewidth=1.0)
                    if np.isfinite(ll) and np.isfinite(peakp): self.signal_ax_width_deriv.hlines(ll,lp,peakp,linestyles=':',linewidth=1.2)
                    if np.isfinite(rl) and np.isfinite(peakp): self.signal_ax_width_deriv.hlines(rl,peakp,rp,linestyles=':',linewidth=1.2)
                    if np.isfinite(W.get('threshold_mm',np.nan)):
                        lo,hi=self.signal_ax_width_deriv.get_ylim(); yy=hi-0.08*(hi-lo)
                        self.signal_ax_width_deriv.annotate('',xy=(lp,yy),xytext=(rp,yy),arrowprops=dict(arrowstyle='<->',linewidth=1.2)); self.signal_ax_width_deriv.text((lp+rp)/2.0,yy,f'dBy/dChannel @ {wthr_pct:.0f}% = {W.get("threshold_mm"):.2f} mm',ha='center',va='bottom',fontsize=8)
                self.signal_ax_width_deriv.text(0.01,0.98,f'dBy/dChannel method = @Threshold; T={wthr_pct:.0f}%\nWidth = pos_R-pos_L = {W.get("threshold_mm",np.nan):.2f} mm',transform=self.signal_ax_width_deriv.transAxes,ha='left',va='top',fontsize=7,bbox=dict(boxstyle='round,pad=0.3',alpha=0.15))
            else:
                ap,bp=W.get('deriv_max_pos_mm',np.nan),W.get('deriv_min_pos_mm',np.nan); av,bv=W.get('deriv_max_value',np.nan),W.get('deriv_min_value',np.nan)
                if np.isfinite(ap) and np.isfinite(av): self.signal_ax_width_deriv.plot(ap,av,marker='^',markersize=7); self.signal_ax_width_deriv.axvline(ap,linestyle='--',linewidth=1.0); self.signal_ax_width_deriv.annotate('MAX',(ap,av),xytext=(5,7),textcoords='offset points',fontsize=8)
                if np.isfinite(bp) and np.isfinite(bv): self.signal_ax_width_deriv.plot(bp,bv,marker='v',markersize=7); self.signal_ax_width_deriv.axvline(bp,linestyle='--',linewidth=1.0); self.signal_ax_width_deriv.annotate('MIN',(bp,bv),xytext=(5,-12),textcoords='offset points',fontsize=8)
                if np.isfinite(ap) and np.isfinite(bp) and np.isfinite(W.get('pp_x2_mm',np.nan)):
                    a,b=sorted((float(ap),float(bp))); lo,hi=self.signal_ax_width_deriv.get_ylim(); yy=hi-0.08*(hi-lo)
                    self.signal_ax_width_deriv.annotate('',xy=(a,yy),xytext=(b,yy),arrowprops=dict(arrowstyle='<->',linewidth=1.2)); self.signal_ax_width_deriv.text((a+b)/2.0,yy,f'P-P = {W.get("pp_x2_mm"):.2f} mm',ha='center',va='bottom',fontsize=8)

        self.signal_ax_width_raw.set_title(f'WIDTH RAW: {wcomp}/Channel | Method: {"P-P" if width_swapped else "@Threshold"}',fontsize=9)
        self.signal_ax_width_deriv.set_title(f'WIDTH DERIVATIVE: d{wcomp}/dChannel | Method: {"@Threshold" if width_swapped else "P-P"}',fontsize=9)

        self.signal_ax_raw.tick_params(labelbottom=False)
        self.signal_ax_width_raw.tick_params(labelbottom=False)
        self.signal_fig.subplots_adjust(left=0.07, right=0.98, bottom=0.12, top=0.90, hspace=0.25, wspace=0.22)
        self.signal_canvas.draw_idle()


    def view_selected_roi(self):
        """Open the selected cropped defect and allow Raw/Derivative display."""
        roi = self.get_selected_roi()
        if roi is None:
            messagebox.showinfo('ROI Viewer', 'Select an ROI first.')
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
            messagebox.showerror('ROI Viewer', 'Dataset for this ROI is not available.')
            return

        # Calculate derivative on FULL signal first, then crop it.
        x, z_raw = ds.get(roi['axis'], roi['odo'], 'Raw')
        mask = (x >= roi['x1']) & (x <= roi['x2'])
        if not np.any(mask):
            messagebox.showerror('ROI Viewer', 'No odometer samples are inside this ROI.')
            return

        ch_indices = self._roi_channel_indices(roi, z_raw.shape[0])
        channel_numbers = (ch_indices + 1).astype(int).tolist()
        xcrop = x[mask]
        raw_crop = z_raw[ch_indices, :][:, mask]

        with np.errstate(divide='ignore', invalid='ignore'):
            deriv_full = np.gradient(z_raw, x, axis=1)
        deriv_full[~np.isfinite(deriv_full)] = 0.0
        deriv_crop = deriv_full[ch_indices, :][:, mask]

        if xcrop.size < 2:
            messagebox.showerror('ROI Viewer', 'ROI is too short to calculate derivative.')
            return

        win = tk.Toplevel(self.root)
        win.title(f"{roi['name']} - Raw / Derivative")
        win.geometry('1100x720')

        control = ttk.Frame(win, padding=6)
        control.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(
            control,
            text=(f"{roi['name']} | Length P-P = "
                  f"{roi['length_mm']:.2f} mm | "
                  f"Length @ Threshold = {roi.get('threshold_length_mm', roi.get('fwhm_mm', np.nan)):.2f} mm | "
                  f"Crop Width = {roi.get('crop_length_mm', np.nan):.2f} mm | "
                  f"Channels {self._roi_channel_label(roi)} | "
                  f"Threshold = {float(roi.get('threshold', 50.0)):.6g}%")
        ).pack(side=tk.LEFT, padx=(0, 12))

        view_mode = tk.StringVar(value='Raw')
        ttk.Label(control, text='Display:').pack(side=tk.LEFT)
        combo = ttk.Combobox(control, textvariable=view_mode, state='readonly',
                             width=11, values=['Raw', 'Derivative'])
        combo.pack(side=tk.LEFT, padx=4)

        fig, ax = plt.subplots(figsize=(10, 6))
        fig.subplots_adjust(left=0.08, right=0.88, bottom=0.12, top=0.90)
        cax = fig.add_axes([0.90, 0.12, 0.022, 0.78])
        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        toolbar = NavigationToolbar2Tk(canvas, win, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)

        state = {'cbar': None}

        def draw_roi(*_):
            ax.clear()
            cax.clear()

            if view_mode.get() == 'Derivative':
                data = deriv_crop.copy()
                title_mode = 'Derivative (full scan -> crop)'
                cbar_label = 'dSignal / dOdometer'
            else:
                data = raw_crop
                title_mode = 'Raw'
                cbar_label = 'Magnetic signal'

            # Threshold is a percentage used for RAW sizing; do not mask data by amplitude.

            lo, hi = np.nanpercentile(data, [2, 98])
            if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
                lo, hi = float(np.nanmin(data)), float(np.nanmax(data))
                if lo == hi:
                    hi = lo + 1.0

            extent = [
                float(xcrop[0]), float(xcrop[-1]),
                0.5, len(channel_numbers) + 0.5
            ]
            im = ax.imshow(
                data, aspect='auto', origin='lower', extent=extent,
                interpolation='nearest', cmap='RdYlGn_r',
                vmin=lo, vmax=hi
            )
            state['cbar'] = fig.colorbar(im, cax=cax)
            state['cbar'].set_label(cbar_label)
            ax.set_xlabel(f"Odometer {roi['odo']} (m)")
            ax.set_ylabel('Physical Channel (ROI circular order)')
            if channel_numbers:
                step = max(1, int(np.ceil(len(channel_numbers) / 15.0)))
                t = np.arange(1, len(channel_numbers) + 1, step, dtype=int)
                ax.set_yticks(t)
                ax.set_yticklabels([str(channel_numbers[i-1]) for i in t])
            ax.set_title(
                f"{roi['file_name']} | {roi['axis']} | {title_mode} | "
                f"Length P-P {roi['length_mm']:.2f} mm"
                if np.isfinite(roi.get('length_mm', np.nan))
                else f"{roi['file_name']} | {roi['axis']} | {title_mode}"
            )

            # Show detected derivative edge positions in both Raw and Derivative view.
            if np.isfinite(roi.get('peak_pos_x', np.nan)):
                ax.axvline(roi['peak_pos_x'], linestyle='--', linewidth=1.5)
            if np.isfinite(roi.get('peak_neg_x', np.nan)):
                ax.axvline(roi['peak_neg_x'], linestyle='--', linewidth=1.5)

            # Threshold-width boundaries are calculated from RAW signal using percentage levels.
            if view_mode.get() == 'Raw':
                left_x = roi.get('threshold_left_x', np.nan)
                right_x = roi.get('threshold_right_x', np.nan)
                left_level = roi.get('threshold_left_level', np.nan)
                right_level = roi.get('threshold_right_level', np.nan)
                peak_x = roi.get('max_raw_x', np.nan)
                if np.isfinite(left_x):
                    ax.axvline(left_x, linestyle=':', linewidth=1.3)
                if np.isfinite(right_x):
                    ax.axvline(right_x, linestyle=':', linewidth=1.3)
                if np.isfinite(left_x) and np.isfinite(peak_x) and np.isfinite(left_level):
                    ax.hlines(left_level, left_x, peak_x, linestyles=':', linewidth=1.3)
                if np.isfinite(right_x) and np.isfinite(peak_x) and np.isfinite(right_level):
                    ax.hlines(right_level, peak_x, right_x, linestyles=':', linewidth=1.3)

            canvas.draw_idle()

        combo.bind('<<ComboboxSelected>>', draw_roi)
        draw_roi()


