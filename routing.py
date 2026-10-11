"""Level-pool routing; SI internally, no extrapolation beyond supplied curves."""
from dataclasses import dataclass, asdict
import math
import numpy as np
import pandas as pd
from scipy.optimize import brentq


class ModelError(ValueError):
    """An actionable input/domain error, safe to display to a user."""


@dataclass(frozen=True)
class Config:
    crest: float = 44.1
    initial: float = 44.1
    width: float = 45.0
    m: float = 0.35
    epsilon: float = 1.0
    sigma: float = 1.0
    g: float = 9.81
    step: float = 1.0
    dz: float = 0.02


def validate_frame(df, columns, kind):
    if not all(c in df for c in columns):
        raise ModelError(f"{kind}: cần các cột {', '.join(columns)}.")
    try:
        a = df[columns].apply(pd.to_numeric, errors='raise').to_numpy(dtype=float)
    except (ValueError, TypeError) as exc:
        raise ModelError(f"{kind}: mọi ô phải là số; không để trống hoặc nhập chữ.") from exc
    if len(a) < 2 or not np.isfinite(a).all():
        raise ModelError(f"{kind}: cần ít nhất 2 dòng số hữu hạn, không có ô trống.")
    a = a[np.argsort(a[:, 0])]
    if np.any(np.diff(a[:, 0]) <= 0):
        raise ModelError(f"{kind}: cột thứ nhất phải tăng nghiêm ngặt, không được trùng.")
    if np.any(a[:, 1] < 0):
        raise ModelError(f"{kind}: cột thứ hai không được âm.")
    if kind == 'V–Z' and np.any(np.diff(a[:, 1]) <= 0):
        raise ModelError('V–Z: dung tích phải tăng nghiêm ngặt theo cao trình.')
    if kind == 'q–Z' and np.any(np.diff(a[:, 1]) < 0):
        raise ModelError('q–Z: lưu lượng phải không giảm theo cao trình.')
    return a


class Reservoir:
    def __init__(self, vz, cfg, rating=None):
        self.cfg = cfg
        if not all(math.isfinite(x) for x in asdict(cfg).values()):
            raise ModelError('Thông số phải là số hữu hạn.')
        if cfg.step <= 0 or cfg.dz <= 0 or cfg.g <= 0:
            raise ModelError('Δt, ΔZ và g phải lớn hơn 0.')
        if cfg.width < 0 or cfg.m <= 0 or not 0 < cfg.epsilon <= 1 or not 0 < cfg.sigma <= 1:
            raise ModelError('B ≥ 0, m > 0; ε và σ phải thuộc (0, 1].')
        self.vz = validate_frame(vz, ['Z (m)', 'V (10^6 m3)'], 'V–Z')
        self.vz[:, 1] *= 1e6
        self.rating = None if rating is None else validate_frame(rating, ['Z (m)', 'q (m3/s)'], 'q–Z')
        self.lo, self.hi = self.vz[0, 0], self.vz[-1, 0]
        if self.rating is not None:
            self.lo = max(self.lo, self.rating[0, 0])
            self.hi = min(self.hi, self.rating[-1, 0])
        if self.lo >= self.hi or not self.lo <= cfg.initial <= self.hi:
            raise ModelError('Z0 phải nằm trong phạm vi chung của bảng V–Z và q–Z (nếu dùng).')
        if self.rating is None and not self.lo <= cfg.crest <= self.hi:
            raise ModelError('Ngưỡng tràn phải nằm trong phạm vi bảng V–Z.')
        count = int(np.ceil((self.hi - self.lo) / cfg.dz)) + 1
        if count > 50000:
            raise ModelError('Bảng phụ trợ quá lớn; tăng ΔZ (tối đa 50.000 mức).')
        knots = [self.vz[:, 0], [cfg.initial, self.lo, self.hi]]
        if self.rating is None:
            knots.append([cfg.crest])
        else:
            knots.append(self.rating[:, 0])
        self.z = np.unique(np.concatenate([np.linspace(self.lo, self.hi, count), *knots]))
        self.z = self.z[(self.z >= self.lo) & (self.z <= self.hi)]
        self.v = self.volume(self.z)
        self.q = self.discharge(self.z)
        self.vref = float(self.volume(cfg.initial))

    def volume(self, z):
        return np.interp(z, self.vz[:, 0], self.vz[:, 1])

    def discharge(self, z):
        if self.rating is not None:
            return np.interp(z, self.rating[:, 0], self.rating[:, 1])
        c = self.cfg
        return c.m * c.epsilon * c.sigma * c.width * np.sqrt(2*c.g) * np.maximum(np.asarray(z)-c.crest, 0)**1.5

    def auxiliary(self, dt=None):
        dt = self.cfg.step * 3600 if dt is None else dt
        dv = self.v - self.vref
        return pd.DataFrame({'Z (m)': self.z, 'H (m)': np.maximum(self.z-self.cfg.crest, 0),
            'V (10^6 m3)': self.v/1e6, 'Delta V (m3)': dv, 'q (m3/s)': self.q,
            'f1 (m3/s)': dv/dt-self.q/2, 'f2 (m3/s)': dv/dt+self.q/2})


def time_grid(t, step):
    """Include every input knot and endpoint to preserve inflow volume/peaks."""
    if (t[-1]-t[0])/step + len(t) > 20000:
        raise ModelError('Quá nhiều bước tính; tăng Δt hoặc rút ngắn chuỗi (tối đa 20.000 điểm).')
    base = np.arange(t[0], t[-1], step)
    candidates = np.sort(np.concatenate([base, t]))
    keep = np.r_[True, np.diff(candidates) > 1e-10]
    return candidates[keep]


def route(inflow, vz, cfg=Config(), method='direct', rating=None):
    if method not in ('direct', 'potapop'):
        raise ModelError('Phương pháp không hợp lệ.')
    r = Reservoir(vz, cfg, rating)
    inflow_a = validate_frame(inflow, ['Time (h)', 'Q (m3/s)'], 'Lũ đến')
    ts = time_grid(inflow_a[:, 0], cfg.step)
    qi = np.interp(ts, inflow_a[:, 0], inflow_a[:, 1])
    z1, v1 = cfg.initial, r.vref
    q1 = float(r.discharge(z1))
    rows = [[ts[0], qi[0], q1, z1, v1, max(z1-cfg.crest, 0), 0, 0, 0, 0, 0, 0]]
    vin = vout = 0.0
    for i in range(1, len(ts)):
        dt = (ts[i]-ts[i-1])*3600
        avg = (qi[i-1]+qi[i])/2
        f1 = (v1-r.vref)/dt - q1/2
        target = avg + f1
        if method == 'potapop':
            f2 = (r.v-r.vref)/dt + r.q/2
            low, high = f2[0], f2[-1]
        else:
            def objective(z):
                return (float(r.volume(z))-r.vref)/dt + float(r.discharge(z))/2 - target
            low, high = objective(r.lo)+target, objective(r.hi)+target
        if target < low-1e-8 or target > high+1e-8:
            direction = 'trên' if target > high else 'dưới'
            raise ModelError(f't = {ts[i]:.4g} h: nghiệm vượt biên {direction} của dữ liệu '
                f'({r.lo:g}–{r.hi:g} m). Bổ sung bảng đặc trưng hoặc giảm Δt nếu hồ đang tháo nhanh. Không ngoại suy.')
        target = np.clip(target, low, high)
        if method == 'potapop':
            z2 = float(np.interp(target, f2, r.z))
            q2 = float(np.interp(z2, r.z, r.q))
        else:
            z2 = brentq(objective, r.lo, r.hi, xtol=1e-11, rtol=1e-13)
            q2 = float(r.discharge(z2))
        v2 = float(r.volume(z2))
        in_step, out_step = avg*dt, (q1+q2)/2*dt
        residual = v2-v1-in_step+out_step
        vin += in_step
        vout += out_step
        hydraulic = q2-float(r.discharge(z2))
        rows.append([ts[i], qi[i], q2, z2, v2, max(z2-cfg.crest, 0), dt/3600,
                     residual, hydraulic, vin, vout, f1])
        z1, v1, q1 = z2, v2, q2
    cols = ['Time (h)', 'Inflow Q (m3/s)', 'Outflow q (m3/s)', 'Elevation Z (m)',
            'Volume V (m3)', 'Head H (m)', 'dt (h)', 'Balance residual (m3)',
            'Rating residual (m3/s)', 'Inflow volume (m3)', 'Outflow volume (m3)', 'f1 start (m3/s)']
    result = pd.DataFrame(rows, columns=cols)
    result['f2 end (m3/s)'] = np.where(result['dt (h)'] > 0,
        (result['Volume V (m3)']-r.vref)/result['dt (h)'].replace(0, np.nan)/3600 + result['Outflow q (m3/s)']/2, np.nan)
    return result


def summarize(df):
    imax = df.loc[df['Inflow Q (m3/s)'].idxmax()]
    omax = df.loc[df['Outflow q (m3/s)'].idxmax()]
    zmax = df.loc[df['Elevation Z (m)'].idxmax()]
    vi, vo = df['Inflow volume (m3)'].iloc[-1], df['Outflow volume (m3)'].iloc[-1]
    dv = df['Volume V (m3)'].iloc[-1]-df['Volume V (m3)'].iloc[0]
    return {'Q đến max (m3/s)': float(imax['Inflow Q (m3/s)']),
        'q xả max (m3/s)': float(omax['Outflow q (m3/s)']), 'Z max (m)': float(zmax['Elevation Z (m)']),
        't đỉnh đến (h)': float(imax['Time (h)']), 't đỉnh xả (h)': float(omax['Time (h)']),
        't Z max (h)': float(zmax['Time (h)']),
        'Giảm đỉnh (%)': float(100*(1-omax['Outflow q (m3/s)']/imax['Inflow Q (m3/s)'])) if imax['Inflow Q (m3/s)'] else None,
        'Trễ đỉnh (h)': float(omax['Time (h)']-imax['Time (h)']),
        'Dung tích tăng max (triệu m3)': float(max(0, df['Volume V (m3)'].max()-df['Volume V (m3)'].iloc[0])/1e6),
        'Tổng đến (triệu m3)': float(vi/1e6), 'Tổng xả (triệu m3)': float(vo/1e6),
        'Thay đổi dung tích (triệu m3)': float(dv/1e6),
        'Sai số tổng cân bằng (m3)': float(dv-vi+vo),
        'Sai số bước max (m3)': float(df['Balance residual (m3)'].abs().max()),
        'Sai số thủy lực max (m3/s)': float(df['Rating residual (m3/s)'].abs().max())}
