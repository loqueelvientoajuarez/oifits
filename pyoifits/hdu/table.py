from .. import utils as _u
from .base import _ValidHDU, _OIFITS1HDU, _OIFITS2HDU

from astropy.io import fits as _fits
import numpy as _np 
import re as _re


def _get_fits_col_dtype(name, col):
    col = asarray(col)
    return (name, col.dtype.str, col.shape[1:])

_fits_types = {
     'i2': '2-bytes int', 'i4': '4-bytes int',
     'f4': '4-bytes float', 'f8': '8-bytes float',
     'c8': '8-bytes complex', 'c16': '16-bytes complex',
     'i1': 'boolean', 'b1': 'boolean'
}
_fits_formats = {
    'i2': 'I', 'i4': 'J',
    'f4': 'E', 'f8': 'D',
    'c8': 'C', 'c16': 'M',
    'i1': 'L', 'b1': 'L',
}

def _dtype_descr(t):
    t = t.strip("|<>") 
    if t[0] in 'SU':
        len_ = int(t[1:])
        type_ = 'string'
    elif m := _re.match('(int|float|complex)([0-9]+)', t):
        len_ = int(m.groups()[1]) // 8
        type_ = m.groups()[0]
    else:
        return _fits_types.get(t, '')
    descr =  f"{len_}-byte{'s' if len_ > 1 else ''} {type_}"
    return descr

def _dtype_to_fits(t, shape):
    t = t.strip("|<>")
    if t[0] in 'SU':
        len_ = int(t[1:])
        fmt = 'A'
    else:
        len_ = 1
        fmt = _fits_formats[t]
    return f"{len_ * int(_np.prod(shape[1:]))}{fmt}"
    

_InheritColumnDescription = _u.InheritConstantArray(
                              '_COLUMNS',
                              dtype=[
                                  ('name', 'U32'),  ('required', bool),
                                  ('type', object), ('shape', object),
                                  ('test', object), ('default', object), 
                                  ('unit', 'U16'),  ('comment', 'U47'),
                              ]
                            )

def _cast_column(col, coldesc):
    val = col.array
    fmt = _dtype_to_fits(coldesc['type'], _np.shape(val))
    col = _fits.Column(name=col.name, array=col.array, format=fmt,
                        unit=coldesc['unit'], null=col.null, dim=col.dim)
    return col

def _cast_columns(cols, colsdesc):
    new_cols = []
    for col in cols:
        coldesc = colsdesc[colsdesc['name'] == col.name]
        if len(coldesc):
            coldesc = coldesc[0]
            spec = _dtype_to_fits(coldesc['type'], _np.shape(col.array))
            real = col.format
            if spec != real:
                try:
                    col = _cast_column(col, coldesc)
                except:
                    pass
        new_cols.append(col)
    return new_cols

def _minimal_fits_column(coldesc, shape, null=None):
    name = coldesc['name']
    dtype = coldesc['type']
    unit = coldesc['unit']
    fmt = _dtype_to_fits(dtype, shape)
    dim = None
    if len(shape) >= 1:
        dim  = shape[1:]
        if fmt[-1] == 'A':
            dim = (int(fmt[:-1]), *dim) 
        dim = str(dim)
    array = _np.ndarray(shape, dtype=dtype)
    col = _fits.Column(name=name, format=fmt, dim=dim, unit=unit) 
    return col

def _merge_fits_columns(oicolumns, *hdus):
    columns = []
    colnames = []
    for hdu in hdus:
        for c in hdu.columns:
            name = c.name
            if name not in colnames:
                colnames.append(name)
                is_oicolumn = oicolumns['name'] == name
                # we want to ensure OI columns have the right format
                # (e.g. too short strings in first table may lead
                # to truncation)
                if is_oicolumn.any():
                    coldesc = oicolumns[is_oicolumn][0]
                    shape = _np.shape(c.array)[1:]
                    null = c.null
                    col = _minimal_fits_column(coldesc, shape, null=null)
                else:
                    col = c
                columns.append(c)
    return columns

def _merge_fits_rows(*rows, id_name=None, equality=lambda x,y: x==y):

    if id_name is None:
        return rows, [{}]

    # New unused IDs (in a sequence, avoiding the ones in either
    rows1 = rows[0]
    id1 = rows1[id_name].tolist()
    kept = [rows1]
    maps = [{}]

    for rows2 in rows[1:]:
        
        id2 = rows2[id_name]
        candidate_id2 = set(range(1, 1 + len(id1) + len(id2)))
        candidate_id2 -= set([*id1, *id2])
        candidate_id2 = sorted(list(candidate_id2))
        
        index_map = {}
        kept_lines = []
        for j, row2 in enumerate(rows2):
            
            equal = [equality(row2, row1) for rows1 in kept for row1 in rows1]
            index_equal = _np.argwhere(equal)
            if len(index_equal):
                index_map[id2[j]] = id1[index_equal[0,0]]
                continue
                
            kept_lines.append(j)
            value = candidate_id2.pop(0) if id2[j] in id1 else id2[j]
            index_map[id2[j]] = value
            id1.append(value)
        kept2 = rows2[kept_lines]
        index_map = {o: n for o, n in index_map.items() if o != n}
        
        kept.append(kept2)
        maps.append(index_map)
        
    return kept, maps

class _OITableHDU(
         _ValidHDU,
         _fits.BinTableHDU,
         _InheritColumnDescription,
      ):

    _REFERENCE_KEY = None

    def __init__(self, data=None, header=None, uint=False, ver=None, 
                    character_as_bytes=False):
        _fits.BinTableHDU.__init__(self, data=data, header=header, uint=uint,
                    ver=ver, character_as_bytes=character_as_bytes)

    def update(self):
        
        super().update()

        header = self.header
        header.set('EXTNAME', self._EXTNAME, 'OIFITS extension name')

        columns = self._get_oi_columns()
        comments = header.comments

        for index, name in enumerate(self.columns.names, start=1):
           
            ttype = f"TTYPE{index}"
            if not comments[ttype]: 
                comment = f"name of column {index}"
                if name in columns['name']:
                    column = columns[columns['name'] == name][0]
                    comment = column['comment']
                comments[ttype] = comment
           
            tform = f"TFORM{index}"
            if not comments[tform]:
                comments[tform] = f"format for {name}"
            
            tunit = f"TUNIT{index}"
            if tunit in header and not comments[tunit]: 
                comments[tunit] = f"unit of {name}"
            
            tdim = f"TDIM{index}"
            if tdim in header and not comments[tdim]:
                comments[tdim] = f"dimension of {name}"
        
        self.add_datasum()
        self.add_checksum()

    @classmethod
    def from_columns(cls, columns, header=None, nrows=0, fill=False,
            character_as_bytes=False):

        # we need to shape the columns to the right type (float type
        # and/or string width)
        oi_columns = cls._get_oi_columns(required=False)
        columns = _cast_columns(columns, oi_columns)

        return super().from_columns(columns, header=header, nrows=nrows,
            fill=False, character_as_bytes=character_as_bytes) 

    def to_version(self, n):

        cls = type(self)

        if cls._OI_VER == n:
            return self.copy()

        for newcls in type(self).__base__.__subclasses__():
            if newcls._OI_VER == n:
                break 
         
        return newcls.from_columns(self.columns)

    @classmethod
    def __init_subclass__(cls):
        super().__init_subclass__()
        if getattr(cls, '_EXTNAME', None) and  getattr(cls, '_OI_REVN', None): 
            _fits.hdu.base._BaseHDU.register_hdu(cls)
 
    @classmethod
    def match_header(cls, header):
        extname = getattr(cls, '_EXTNAME', None)
        oi_revn = getattr(cls, '_OI_REVN', None)
        if extname is None or oi_revn is None:
            return NotImplementedError
        return (_fits.BinTableHDU.match_header(header) and
                header.get('EXTNAME', '') == extname and
                header.get('OI_REVN', '') == oi_revn)

    def append_lines(self, lines):
      
        merged_data = _np.hstack([self.data, lines]) 
        merged = type(self)(data=merged_data, header=self.header)

        return merged
    
    def __and__(self, other):

        return getattr(other, '_EXTNAME', '') == getattr(self, '_EXTNAME', None)

    def __mod__(self, other):

        h1, h2 = self.header, other.header

        return (self & other and
                h1.get('INSNAME', '') == h2.get('INSNAME', '') and
                h1.get('ARRNAME', '') == h2.get('ARRNAME', '') and
                h1.get('CORRNAME', '') == h2.get('CORRNAME', ''))
 
    def _xmatch(self, name, refhdu, refname, concatenate=False):
        """Helper to find target or array properties from indices"""
        
        ref_values = getattr(refhdu, name)
        ref_indices = getattr(refhdu, refname)
        xmatch = dict(zip(ref_indices, ref_values))
        indices = getattr(self, refname)
        shape = indices.shape + _np.shape(ref_values[0])
        values = _np.reshape([xmatch[i] for i in indices.flatten()], shape)
      
        if concatenate:
            values = [_np.atleast_1d(a) for a in values]
            values = ['-'.join([str(x) for x in a]) for a in values]

        return values

    def data_shape(self):

        nrows = len(self.data)
        
        # is there some wavelength data?
        colnames = self._get_spec_colnames()
        if not colnames:
            return (nrows,)

        return self.data[colnames[0]].shape

    def get_nwaves(self):

       return 0 

    def rename_columns(self, **names):
        
        self.data.dtype.names = [names.get(n, n) for n in self.data.dtype.names]
        for old, new in names.items():
            self.columns[old].name = new
        self.update()
 
    def _verify(self, option='warn'):
        
        errors = super()._verify(option)

        OI_COLUMNS = self._get_oi_columns(required=False)

        # Check all required columns are present
        for c in self._get_oi_colnames(required=True):
            if c not in self.data.names:
                name = self.__class__.__name__
                err_text = f"Missing column '{c}' in {name} object"
                err = self.run_option(option, err_text, fixable=False)
                errors.append(err)
           
        # Check column types
        column_casts = []
        for coldesc in OI_COLUMNS:
            name, req, type_, shape, test, default, unit, comment = coldesc
            if name not in self.columns.names:
                continue
            
            # check the type
            dtype = self.data[name].dtype
            spec = _dtype_descr(type_)
            real = _dtype_descr(dtype.str)
            if spec != real:
                err_txt = f"Column {name}: type must be {spec} but is {real}."
                fix_txt = "Will try to fix."
                column_casts.append(name)
                def fix(): pass
                err = self.run_option(option, err_txt, fix_txt, fix)
                errors.append(err)

            # check unit
            real = self.columns[name].unit
            spec = unit
            if real != spec:
                err_txt = f"Column {name}: unit must be {spec} but is {real}."
                fix_txt = "Fixed." 
                def fix(col=self.columns[name]): col.unit = spec
                err = self.run_option(option, err_txt, fix_txt, fix)
                errors.append(err)
            
            # check dimensionality
            dshape = self.data.dtype[name].shape
            if _u.NW in shape:
                nwave = self.get_nwaves()
                shape = tuple(nwave if d == _u.NW else d for d in shape)
            if shape != dshape:
                err_txt = f"Column {name}: shape is {dshape}, should be {shape}"
                err = self.run_option(option, err_txt, fixable=False) 
                errors.append(err)
            
            # Check values
            if test is not None:
                values = self.data[name]
                invalid = _np.array([not test(v) for v in _np.nditer(values)])
                invalid = invalid.reshape(values.shape)
                if invalid.any():
                    fixable = default is not None
                    if fixable:
                        try:
                            default = _np.array(default, dtype=dtype)
                            def fix(): values[invalid] = default
                        except:
                            fixable = False
                    if not fixable:
                        fix = None
                    val1 = values[invalid][0]
                    err_text = f"Column '{name}' has incorrect values. First encountered  '{val1}'."
                    fix_text = f"Replaced by default value"
                    err = self.run_option(option, err_text, fix_text, fix, fixable)
        # Non standard columns should start have prefix_
        colnames = self.data.dtype.names
        oi_colnames = self._get_oi_colnames()
        subst = {name: f"NS_{name}" for name in colnames 
                    if name not in oi_colnames and '_' not in name}
        if subst:
            nonstd = ', '.join([f"'{n}'" for n in subst.keys()])
            err_text = f"Column name(s) should start with prefix_ :'{nonstd}'."
            fix_text = "NS_ has been prefixed to column name(s)"
            def fix(h=self): h.rename_columns(**subst)
            err = self.run_option(option, err_text, fix_text, fix)
            errors.append(err)

        #cast_done = False
        if len(column_casts):
            columns = _cast_columns(self.columns, OI_COLUMNS)
            self.data = _fits.FITS_rec.from_columns(columns)
            self.update()

        return errors

    def __repr__(self):

        return f"<{type(self).__name__} at {hex(id(self))} ({self._diminfo()})>"
   
    def __str__(self):
        
        return f"<{type(self).__name__} ({self._diminfo()})>"
 
    # Quick access to OICOLUMNS with hdu.VI2DATA, etc.
    def __getattr__(self, s):
      
        colnames = self._get_oi_colnames() 
        oicolnames = [x for x in self.columns.names if x in colnames]
        if s in oicolnames:
            return self.data[s][...]
        
        clsname = type(self).__name__
        err = f"'{clsname}' object has no attribute '{s}'"
        raise AttributeError(err)

    def zero(self):
        newhdu = self.copy()
        for name in self._get_spec_colnames():
            newhdu.data[name][...] = 0
        return newhdu
    
    def _diminfo(self):
        
        ncols = len(self.columns)
        nrows, *nwave = self.data_shape()
        if len(nwave):
            return f"{ncols}C×{nrows}R×{nwave[0]}W" 
        return f"{ncols}C×{nrows}R" 

    def _resize_data(self, x, shape='none', flatten=False, copy=True):
  
        data_shape = self.data_shape()
        if len(data_shape) == 1 or x is None:
            return x
        
        if shape == 'none':
            target_shape = ()
        elif shape == 'table':
            target_shape = (len(self.data),)
        elif shape == 'data':
            target_shape = data_shape
        else:
            raise ValueError(f"shape incorrect: '{shape}'")

        x_shape = _np.shape(x)
        if target_shape:
    
            if not x_shape: # scalar
                x = _np.full(target_shape, x)
            elif x_shape[0] == target_shape[0]:
                if len(target_shape) == 2:
                    x = _np.full((target_shape[1:] + x_shape), x).swapaxes(0,1)
            else:
                msg = f"dimension mismatch: {x_shape} and {target_shape}"
                raise ValueError(msg)

            if flatten:
                target_len = _np.prod(target_shape)
                flat_shape = (target_len, *x.shape[len(target_shape):])
                x = x.reshape(flat_shape)

        elif x_shape:

            x = x.copy()

        return x


    @classmethod
    def _get_oi_columns(cls, required=False, condition=None):
        cols = cls._COLUMNS
        if required:
            cols = cols[cols['required']]
        if condition is not None:
            cols = [c for c in cols if condition(c)]
        return cols
    
    @classmethod
    def _get_oi_colnames(cls, required=False, condition=None):
        cols = cls._get_oi_columns(required, condition)
        names = [c[0] for c in cols]
        return names
    
    @classmethod
    def _get_spec_columns(cls, required=False):
        return cls._get_oi_columns(required, lambda c: c[3] == ('NWAVE',))
    
    @classmethod
    def get_error_names(cls, required=False):
        cols = cls._get_spec_colnames(required)
        return [c for c in cols if c[-3:] == 'ERR']

    @classmethod
    def get_observable_names(cls, required=False):
        cols = cls._get_spec_colnames(required)
        return [c for c in cols if c[-3:] != 'ERR' and c != 'FLAG']
    
    @classmethod
    def _get_spec_colnames(cls, required=False):
        cols = cls._get_spec_columns(required)
        return [c[0] for c in cols]

    def merge(self, *others):
        return self._merge_helper(*others)

    def _merge_helper(self, *others, id_name=None, equality=lambda a, b: None):
        """Merge a set of OIFITS tables of the same kind.  id_name: column
ID that must be kept unique. equality: criteria to discard redundant rows.
        """

        # Check we are merging the same type of extension 
        ext1 =  self.header['EXTNAME']
        for other in others:
            ext2 = other.header['EXTNAME']
            if ext1 != ext2:
                txt = 'cannot merge FITS extensions {ext1} with {ext2}' 
                raise TypeError(txt)

        # Determine class when merging different revisions of a table
        hdus = [self, *others]
        i_maxrevn = _np.argmax([x._OI_REVN for x in hdus])
        cls = type(hdus[i_maxrevn])

        # Merged tables will keep all columns.  Values will be zero if not 
        # defined in one of the tables
        columns = _merge_fits_columns(cls._COLUMNS, *hdus)
        colnames = [c.name for c in columns]

        # Merge sets of FITS rows.
        # * In each set, rows duplicating one of the previous set is eliminated
        # * For each set a map of old_id -> new_id is built to avoid
        #   duplicate IDs.
        rows = [hdu.data for hdu in hdus]
        rows, maps = _merge_fits_rows(*rows, id_name=id_name, equality=equality)
        nrows = sum(len(r) for r in rows)

        # Merge headers.  
        headers = [hdu.header for hdu in hdus]
        req_keys = cls._CARDS['name'][cls._CARDS['required']]
        header = _u.merge_fits_headers(*headers, req_keys=req_keys)
        
        # Create an empty merged fits with the right number of rows,
        # then fill it.
        #
        # FIXME null values!
        #
        
        merged = cls.from_columns(columns, nrows=nrows, fill=1, header=header)
        
        rowmin = 0
        for data, map in zip(rows, maps):
            ndata = len(data)
            rowmax = rowmin + ndata
            for name in data.names:
                if map and name == id_name:
                    values = [map.get(i, i) for i in data[name]]
                else:
                    values = data[name]
                merged.data[name][rowmin:rowmax][...] = values 
            rowmin += ndata

        # Update in HDUs refering to other
        for hdu, map in zip(hdus, maps):
            if map and (container := getattr(hdu, '_container', None)):
                for h in container.get_OITableHDUs():
                    if h.refers_to(hdu): 
                        field = h.data[id_name]
                        for old, new in map.items():
                            field[field == old] = new
        
        return merged 

    def refers_to(self, other):
        """Whether an OIFITS table makes a reference to another one via
        ARRNAME, INSNAME, or CORRNAME"""
        return other.is_referred_to_by(self)
    
    def is_referred_to_by(self, other):
        """Whether an OIFITS table is a reference for another table via
        ARRNAME, INSNAME, or CORRNAME"""
        return False

    def __eq__(self, other):

        if not isinstance(other, _OITableHDU):
            return False

        header1, header2 = self.header, other.header
        data1, data2 = self.data, other.data

        return (header1['EXTNAME'] == header2['EXTNAME'] and
                header1.get('INSNAME', '') == header2.get('INSNAME', '') and
                header1.get('ARRNAME', '') == header2.get('ARRNAME', '') and
                header1.get('CORRNAME', '') == header2.get('CORRNAME', '') and
                len(data1) == len(data2) and 
                data1.dtype == data2.dtype and
                (data1 == data2).all())
    
    @classmethod
    def from_data(cls, *, version=None, fits_keywords={}, **columns):

        if not hasattr(cls, '_OI_VER'):
            if version is None:
                version = getattr(cls, '_OI_VER', 2)
            cls = cls.get_class(version=version)

        # match case
        fits_keywords = {k.upper(): v for k, v in fits_keywords.items()
                                                    if v is not None}
        columns = {k.upper(): v for k, v in columns.items()}
        
        # Header
        header = _fits.Header()
        for card in cls._CARDS:
            name = card['name']
            comment = card['comment']
            if name in fits_keywords:
                header.set(name, fits_keywords[name], comment)
                del fits_keywords[name]
            elif card['required']:
                if card['default'] is not None:
                    header.set(name, card['default'], comment)
        for name, value in fits_keywords.items():
            if not isinstance(value, (tuple, list)):
                value = [value]
            header.set(name, *value)
    
        def reshape_to_rows(x, nrows):
            shape = _np.shape(x)
            if not shape or shape[0] != nrows:
                return _np.full((nrows, *shape), x)
            else:
                return _np.asarray(x)
    
        # Table
        fcols = []
        nrows = max(len(_np.atleast_1d(c)) for c in columns.values())
            
            # official OIFITS columns
        for col in cls._COLUMNS:
            name = col['name']
            if name not in columns:
                if col['required']:
                    columns[name] = col['default']
                else:
                    continue
            array = reshape_to_rows(columns[name], nrows)
            del columns[name]
            dtype = col['type']
            unit = col['unit']
            shape = _np.shape(array)
            fmt = _dtype_to_fits(dtype, shape)
            fcol = _fits.Column(format=fmt, unit=unit, array=array, name=name)
            fcols.append(fcol)   

            # additional columns
        for name in columns:
            array = reshape_to_rows(columns[name], nrows)
            dtype = array.dtype
            shape = array.shape
            fmt = _dtype_to_fits(dtype, shape)
            fcol = _fits.Column(array=array, format=fmt, name=name) 
            fcols.appen(fcol)
        
        tab = super().from_columns(fcols, header=header)
        return tab


class _OITableHDU1(_OITableHDU):
    _OI_REVN = 1
    _CARDS = [('OI_REVN', True, _u.is_one, 1, 
        '1st revision of this table in OIFITS format')]

class _OITableHDU2(_OITableHDU):
    _OI_REVN = 2
    _CARDS = [('OI_REVN', True, _u.is_two, 2, 
        '2nd revision of this table in OIFITS format')]

_InitialisedLater = None

class _OITableHDU11(
        _OIFITS1HDU,
        _OITableHDU1
      ):
    pass

class _OITableHDU21(
        _OIFITS2HDU,
        _OITableHDU1
      ):
    pass

class _OITableHDU22(
        _OIFITS2HDU,
        _OITableHDU2
      ):
    pass
