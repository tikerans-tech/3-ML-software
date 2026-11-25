import os
import csv
import json
import zipfile
import tempfile
import shutil
import re
import pickle
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.widgets import RectangleSelector
from matplotlib.patches import Rectangle
from matplotlib.colors import TwoSlopeNorm
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from scipy.signal import find_peaks
from openpyxl import load_workbook
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor
from sklearn.model_selection import train_test_split, LeaveOneOut, cross_val_predict
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from sklearn.linear_model import Ridge

