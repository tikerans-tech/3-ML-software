from .common import *


class MFLData:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.odometers = {}
        self.signals = {}
        # Global magnetic-signal offset applied to Raw Bx/By/Bz.
        # Default requested value = +3. Derivative signals are unchanged by a constant offset.
        self.offset = 3.0

        # Optional automatic per-channel zero-offset equalization.
        # When enabled, each Hall channel is shifted so its robust baseline
        # matches the common baseline of all channels for that component.
        # This removes fixed sensor-to-sensor DC offset without changing the
        # shared magnetic-field level. Offsets are cached because signals are static.
        self.auto_sensor_offset = False
        self._sensor_offset_cache = {}

        self._load()


    @staticmethod
    def _parse_numeric_row(line):
        parts = [p.strip() for p in line.strip().split(',')]
        vals = []
        for p in parts:
            if p == '':
                continue
            try:
                vals.append(float(p))
            except ValueError:
                pass
        return np.asarray(vals, dtype=float)


    def _load(self):
        with open(self.path, 'r', encoding='utf-8-sig', errors='ignore') as f:
            lines = [line.rstrip('\n\r') for line in f]

        # Odometers: label line followed by one numeric row
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith('Odometer :'):
                try:
                    no = int(s.split(':', 1)[1].split(',')[0].strip())
                except Exception:
                    continue
                if i + 1 < len(lines):
                    arr = self._parse_numeric_row(lines[i + 1])
                    if arr.size:
                        self.odometers[no] = arr

        # Hall blocks: each block is label + numeric rows until next Hall label/end
        labels = {
            'Axial Hall': 'X',
            'Circ. Hall': 'Y',
            'Radial Hall': 'Z',
        }
        hall_positions = []
        for i, line in enumerate(lines):
            key = line.strip()
            if key in labels:
                hall_positions.append((i, labels[key]))

        for j, (start, axis) in enumerate(hall_positions):
            end = hall_positions[j + 1][0] if j + 1 < len(hall_positions) else len(lines)
            rows = []
            for line in lines[start + 1:end]:
                arr = self._parse_numeric_row(line)
                if arr.size > 2:
                    rows.append(arr)
            if rows:
                n = min(len(r) for r in rows)
                rows = [r[:n] for r in rows]
                self.signals[axis] = np.vstack(rows)

        if not self.signals:
            raise ValueError('ไม่พบข้อมูล Axial/Circ./Radial Hall ในไฟล์')
        if not self.odometers:
            raise ValueError('ไม่พบข้อมูล Odometer ในไฟล์')


    def _channel_equalization_offsets(self, axis):
        """Return one fixed DC correction value per physical Hall channel.

        Automatic method:
        1) Estimate each channel baseline with the median over the full scan.
           Median is used so sparse defects/spikes have limited influence.
        2) Find the common baseline = median of all channel baselines.
        3) Correction_i = baseline_i - common_baseline.

        Applying ``z - correction[:, None]`` makes all channels share the same
        baseline while preserving the common absolute field level. This is
        intentionally different from the user Global Offset, which is applied
        after equalization to every channel equally.
        """
        if axis in self._sensor_offset_cache:
            return self._sensor_offset_cache[axis]

        if axis not in self.signals:
            return np.asarray([], dtype=float)

        raw = np.asarray(self.signals[axis], dtype=float)
        if raw.ndim != 2 or raw.shape[0] == 0:
            return np.asarray([], dtype=float)

        with np.errstate(invalid='ignore'):
            baselines = np.nanmedian(raw, axis=1)

        baselines = np.asarray(baselines, dtype=float)
        finite = np.isfinite(baselines)
        if not np.any(finite):
            corr = np.zeros(raw.shape[0], dtype=float)
        else:
            common = float(np.nanmedian(baselines[finite]))
            corr = baselines - common
            corr[~np.isfinite(corr)] = 0.0

        self._sensor_offset_cache[axis] = corr
        return corr


    def set_auto_sensor_offset(self, enabled):
        """Enable/disable automatic per-channel sensor offset correction."""
        self.auto_sensor_offset = bool(enabled)


    def get(self, axis='X', odo_no=1, mode='Raw'):
        if axis not in self.signals:
            raise ValueError(f'ไม่พบข้อมูลแกน {axis}')
        if odo_no not in self.odometers:
            raise ValueError(f'ไม่พบ Odometer {odo_no}')

        z = self.signals[axis].copy()

        # Optional automatic sensor-by-sensor DC offset equalization.
        # This correction is applied BEFORE the global offset and before any
        # Raw/Derivative/ROI/AI analysis so every downstream calculation sees
        # the same calibrated signal.
        if bool(getattr(self, 'auto_sensor_offset', False)):
            corr = self._channel_equalization_offsets(axis)
            if corr.size == z.shape[0]:
                z = z - corr[:, None]

        # Apply the dataset-wide constant offset before any downstream analysis.
        # For Derivative mode, the derivative of a constant is zero, so dB/dx and
        # dB/dChannel amplitudes are not shifted by this offset.
        z = z + float(getattr(self, 'offset', 0.0))
        x = self.odometers[odo_no].copy()
        n = min(z.shape[1], x.size)
        z = z[:, :n]
        x = x[:n]

        # Ensure increasing x for plotting/selection
        if x.size > 1 and np.nanmedian(np.diff(x)) < 0:
            x = x[::-1]
            z = z[:, ::-1]

        if mode == 'Derivative':
            # Spatial derivative along odometer direction for each channel
            with np.errstate(divide='ignore', invalid='ignore'):
                z = np.gradient(z, x, axis=1)
            z[~np.isfinite(z)] = 0.0

        return x, z


