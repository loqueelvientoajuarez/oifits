from .table import _OITableHDU, _OITableHDU11, _OITableHDU22
from .. import utils as _u

import numpy as _np


__all__ = ["TargetHDU1", "TargetHDU2"]

_milliarcsec = _np.deg2rad(1) / 3_600_000

class _MustHaveTargetHDU(_OITableHDU):

    def _get_target_field(self, name, shape='none', flatten=False,
            default=None):

        refhdu = self.get_targetHDU()
        if refhdu is None:
            val = default
        else:
            val = self._xmatch(name, refhdu, 'TARGET_ID')
        return self._resize_data(val, shape, flatten)

    def get_target(self, shape='none', flatten=False, default='N/A'):
        obj = self._container[0].header.get('OBJECT', default)
        if obj != 'MULTI':
            default = obj
        return self._get_target_field('TARGET', shape, flatten, default)
    def get_equinox(self, shape='none', flatten=False):
        return self._get_target_field('EQUINOX', shape, flatten)
    def get_ra(self, shape='none', flatten=False):
        return self._get_target_field('RAEP0', shape, flatten)
    def get_dec(self, shape='none', flatten=False):
        return self._get_target_field('DECEP0', shape, flatten)
    def get_parallax(self, shape='none', flatten=False):
        return self._get_target_field('PARALLAX', shape, flatten)
    def get_pmra(self, shape='none', flatten=False):
        return self._get_target_field('PMRA', shape, flatten)
    def get_pmdec(self, shape='none', flatten=False):
        return self._get_target_field('PMDEC', shape, flatten)
    def get_rv(self, shape='none', flatten=False):
        return self._get_target_field('SYSVEL', shape, flatten)
    def get_spectype(self, shape='none', flatten=False):
        return self._get_target_field('SPECTYP', shape, flatten)
    def get_category(self, shape='none', flatten=False):
        return self._get_target_field('CATEGORY', shape, flatten)
    
    def get_targetHDU(self):
        return self._container.get_targetHDU()

    def _verify(self, option='warn'):

        errors = super()._verify(option)

        # Verify Target ID is correct (> 0) and referenced

        val = _np.unique(self.TARGET_ID)
        if not all(val >= 1):
            err_text = "'TARGET_ID' should be ≥ 1"
            err = self.run_option(option, err_text, fixable=False)
            errors.append(err)

        t = self.get_targetHDU()
        if t is not self:
            for v in val:
                if v not in t.TARGET_ID:
                    err_text = f"'TARGET_ID' not refered in TargetHDU: {v}"
                    err = self.run_option(option, err_text, fixable=False)
                    errors.append(err)

        return errors


def _is_veltyp(s):
    return s in ['LSR', 'HELIOCEN', 'BARYCENTR', 'TOPOCENT']

def _is_veldef(s):
    return s in ['OPTICAL', 'RADIO']

class _TargetHDU(_MustHaveTargetHDU):
    _EXTNAME = 'OI_TARGET' 
    _COLUMNS = [
        ('TARGET_ID',  True, '>i2',  (), _u.is_strictpos, None, None),
        ('RAEP0',      True, '>f8',  (), None,            None, "deg"), 
        ('DECEP0',     True, '>f8',  (), None,            None, "deg"), 
        ('EQUINOX',    True, '>f4',  (), None,            None, "yr"),
        ('RA_ERR',     True, '>f8',  (), None,            0.,   "deg"),  
        ('DEC_ERR',    True, '>f8',  (), None,            0.,   "deg"),
        ('SYSVEL',     True, '>f8',  (), None,            None, "m/s"), 
        ('VELTYP',     True, '<U8',  (), _is_veltyp,      None, None), 
        ('VELDEF',     True, '<U8',  (), _is_veldef,      None, None),
        ('PMRA',       True, '>f8',  (), None,            0.,   "deg/yr"), 
        ('PMDEC',      True, '>f8',  (), None,            0.,   "deg/yr"),
        ('PMRA_ERR',   True, '>f8',  (), None,            0.,   "deg/yr"), 
        ('PMDEC_ERR',  True, '>f8',  (), None,            0.,   "deg/yr"),
        ('PARALLAX',   True, '>f4',  (), None,            None, "deg"), 
        ('PARA_ERR',   True, '>f4',  (), None,            0.,   "deg"),
    ]
    
    def _verify(self, option='warn'):

        errors = super()._verify(option)

        target_id = self.TARGET_ID
        if len(_np.unique(target_id)) == len(target_id):
            return errors

        err_text = f"Repeated TARGET_ID in {type(self).__name__}"
        err = self.run_option(option, err_text, fixable=False)
        errors.append(err)

        return errors
    
    def _argwhere_same_target(self, t2, max_distance=10 * _milliarcsec):
        indices = _np.logical_and(
                      self.TARGET == t2['TARGET'],
                      self.EQUINOX == t2['EQUINOX'],
                      abs(self.RAEP0 - t2['RAEP0']) < max_distance,
                      abs(self.DECEP0 - t2['DECEP0']) < max_distance
                  )
        return _np.argwhere(indices)
                
    def _merge(self, hdu2, max_distance=10 * _milliarcsec):

        # re-index first HDU
        old_id1 = self.TARGET_ID
        new_id1 = _np.arange(1, 1 + len(old_id1)) 
        
        # append second HDU, but only lines that are different
        i = 1 + len(old_id1)
        old_id2 = hdu2.TARGET_ID
        new_id2 = _np.zeros_like(old_id2)
        kept_lines = []
        for j, t2 in enumerate(hdu2.data):
            where = hdu1._argwhere_same_target(t2, max_distance=max_distance)
            if len(where):
                new_id2[j] = old_id1[where[0,0]] 
            else:
                new_id2[j] = i
                i += 1
                kept_lines.append(j)
        
        # merged table
        merged = self + hdu2.data[kept_lines] 
        merged.TARGET_ID = _np.hstack(new_id1, new_id2[kept_lines])
        
        # maps old to new indices for each table
        map1 = {o: n for o, n in zip(old_id1, new_id1)}
        map2 = {o: n for o, n in zip(old_id2, new_id2)}
        
        return merged, map1, map2
 
def _is_category(s):
    return s in ['SCI', 'CAL']

class TargetHDU1(
        _TargetHDU,
        _OITableHDU11, # OIFITS1, table rev. 1
      ):
    _COLUMNS = [
        ('TARGET',  True, '<U16', (), _u.is_nonempty, None, None),
        ('SPECTYP', True, '<U16', (), None,           None, None),
    ]

class TargetHDU2(
        _TargetHDU, 
        _OITableHDU22, # OIFITS2, table rev. 2
      ):
    _COLUMNS = [
        ('TARGET',   True,  '<U32', (), _u.is_nonempty, None,  None),
        ('SPECTYP',  True,  '<U32', (), None,           None,  None),
        ('CATEGORY', False, '<U3',  (), _is_category,   'SCI', None),
    ]
