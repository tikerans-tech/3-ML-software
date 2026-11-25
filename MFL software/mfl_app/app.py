from .common import *
from .data import MFLData
from .ui import UiMixin
from .datasets import DatasetsMixin
from .cscan import CscanMixin
from .roi import RoiMixin
from .signal_view import SignalViewMixin
from .ai import AiMixin
from .project_io import ProjectIoMixin

class MultiDefectCSCANApp(UiMixin, DatasetsMixin, CscanMixin, RoiMixin, SignalViewMixin, AiMixin, ProjectIoMixin):
    def view_3d_defect(self):
        self.lower_view_var.set('3D Pipe Defect')
        self.switch_lower_view()

    def __init__(self, root):
        self.root = root
        self.root.title('MFL Multi-Defect C-scan / Trace Crop Tool v48 - v44 UI + Actual/AI')
        self.root.geometry('1500x900')

        self.datasets = []
        self.current = None
        self.selector = None
        self.rois = []
        self.roi_artists = []
        self.roi_counter = 0

        self.file_var = tk.StringVar()
        self.axis_var = tk.StringVar(value='X')
        self.mode_var = tk.StringVar(value='Raw')
        self.odo_var = tk.IntVar(value=1)
        self.vmin_var = tk.StringVar(value='')
        self.vmax_var = tk.StringVar(value='')
        # Value mapped to the yellow midpoint of RdYlGn_r. Blank = midpoint of min/max.
        self.vcenter_var = tk.StringVar(value='')
        # One global offset used by every loaded dataset and every Raw Bx/By/Bz calculation.
        self.global_offset_var = tk.StringVar(value='3')
        # Automatic per-channel Hall-sensor baseline equalization.
        # Default OFF so legacy projects/data remain unchanged until explicitly enabled.
        self.auto_sensor_offset_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value='Open CSV files to begin.')
        self.length_threshold_var = tk.StringVar(value='50.0')
        self.width_threshold_var = tk.StringVar(value='50.0')
        # User-specified number of defects inside the selected ROI. 1 = legacy/single defect.
        self.roi_defect_count_var = tk.IntVar(value=1)
        self.depth_var = tk.StringVar(value='')
        self.wall_thickness_var = tk.StringVar(value='12.7')
        self.anomaly_class_var = tk.StringVar(value='Set WT')
        self.ext_int_var = tk.StringVar(value='External')
        self.length_selected_method_var = tk.StringVar(value='Bx Length P-P')
        self.width_selected_method_var = tk.StringVar(value='Bx Width P-P')
        # Signal components used in the embedded ROI viewer.
        # Length can be inspected from Bx or Bz; Width can be inspected from Bx or By.
        self.length_plot_component_var = tk.StringVar(value='Bx')
        self.width_plot_component_var = tk.StringVar(value='Bx')
        # Number of consecutive channels visible in the C-scan.
        # The vertical C-scan scrollbar moves this window one channel at a time.
        self.visible_channels_var = tk.IntVar(value=20)
        # Physical channel shown at display-row 1 (bottom of the C-scan).
        # Changing this value ROTATES the channel order circularly, e.g.
        # Ch 68,69,70,1,2,3,... so defects crossing Last/Ch1 stay connected.
        self.channel_start_var = tk.IntVar(value=1)
        # C-scan display processing only. Numerical ROI calculations continue to use original data.
        self.display_processing_var = tk.StringVar(value='Raw')
        # Main C-scan visualization style: conventional color map or stacked trace/waterfall view.
        self.cscan_view_var = tk.StringVar(value='Color C-scan')
        # ROI table columns can be shown/hidden without changing stored data.
        # The actual column definitions are initialized in _build_ui().
        self.table_columns = ()
        self.table_column_labels = {}
        self.table_column_vars = {}
        self.table_default_columns = ()
        self._table_columns_window = None
        self._n_channels = 0
        self._channel_display_order_cache = np.asarray([], dtype=int)
        # Keep extracted self-contained project data alive for the current session.
        self._project_temp_dirs = []

        # AI depth model. Training workbook columns expected:
        # Max Raw | Ext/Int | Length | Width | Depth | Velocity | Thickness
        self.ai_training_path_127_var = tk.StringVar(value='')
        self.ai_training_path_1031_var = tk.StringVar(value='')
        # Legacy alias for old code paths; new UI uses the two variables above.
        self.ai_training_path_var = self.ai_training_path_127_var
        self.ai_velocity_var = tk.StringVar(value='0.7')
        self.ai_status_var = tk.StringVar(value='AI model: not trained')
        # Separate AI depth models by wall-thickness family.
        # Two completely independent models: WT 12.70 mm and WT 10.31 mm
        # for backward compatibility with older calibration projects.
        self.ai_models = {}
        self.ai_model_infos = {}
        self.ai_model = None  # active-model alias used by legacy code paths
        self.ai_model_info = {}  # active-model info alias

        # Actual reference dimensions by ROI number. Two reference sets are
        # available, selected automatically from the global wall thickness.
        # ROI > 26 has no reference and is intentionally not used for the
        # actual-comparison/AI prediction workflow requested here.
        self.actual_reference_sets = {
            12.70: [
                (9.75,9.53,8.26),(9.76,9.74,7.27),(9.75,9.56,6.60),(9.60,9.61,5.29),
                (9.41,9.41,3.85),(9.30,9.67,3.12),(9.25,8.87,2.15),(9.45,8.87,1.12),
                (28.40,20.25,0.95),(29.19,23.69,1.95),(28.84,25.14,3.19),(28.07,26.31,4.50),
                (29.45,26.70,5.35),(29.27,27.56,6.48),(29.06,28.21,7.37),(29.21,28.00,8.13),
                (19.38,22.56,5.46),(23.09,19.96,5.04),(19.45,19.26,8.39),(18.91,19.30,7.31),
                (19.31,19.23,6.69),(19.45,17.99,4.69),(19.03,18.38,4.30),(18.97,18.14,4.43),
                (19.29,16.90,2.18),(17.78,15.64,1.15),
            ],
            10.31: [
                (9.63,10.09,10.19),(9.93,9.69,8.55),(9.72,9.73,7.71),(9.75,9.71,6.52),
                (9.74,9.77,5.39),(9.64,9.39,4.11),(9.29,9.42,2.60),(9.51,8.56,1.18),
                (28.35,21.58,1.27),(28.68,23.40,2.53),(29.64,26.25,4.35),(29.06,27.08,5.52),
                (29.96,28.33,6.82),(29.46,26.82,7.93),(29.50,28.32,9.58),(29.77,28.76,10.84),
                (19.42,22.55,6.62),(23.73,19.62,6.26),(19.71,19.67,9.88),(19.80,19.53,8.97),
                (19.54,19.31,7.64),(19.50,18.86,6.20),(19.25,18.95,4.92),(19.55,18.35,3.62),
                (19.19,17.81,2.52),(19.08,16.51,1.26),
            ],
        }

        self._build_ui()


