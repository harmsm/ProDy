# -*- coding: utf-8 -*-
# ProDy: A Python Package for Protein Dynamics Analysis
# 
# Copyright (C) 2010-2012 Ahmet Bakan
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#  
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>

"""This module defines classes for handling atomic data.

.. _atomic:
    
Atomic data
===============================================================================

ProDy stores atomic data in instances of :class:`AtomGroup` class.  This
class is designed to be efficient and responsive, i.e. facilitates user
to access atomic data quickly for any subset of atoms.  An :class:`AtomGroup`
instance can be obtained by parsing a PDB file as follows: 
    
>>> from prody import *
>>> ag = parsePDB('1aar')

To read this page in a Python session, type:
    
>>> # help(atomic)

:class:`AtomGroup` instances can store multiple coordinate sets, which may
be models from an NMR structure, snapshots from an MD simulation.


ProDy stores all atomic data in :class:`AtomGroup` instances and comes
with other classes acting as pointers to provide convenient read/write access 
to such data.  These classes are:

* :class:`Atom` - Points to a single atom in an :class:`AtomGroup` instance.                          

* :class:`Selection` - Points to an arbitrary subset of atoms. See 
  :ref:`selections` and :ref:`selection-operations` for usage examples.

* :class:`Chain` - Points to atoms that have the same chain identifier.

* :class:`Residue` - Points to atoms that have the same chain identifier, 
  residue number and insertion code.
                      
* :class:`AtomMap` - Points to arbitrary subsets of atoms while allowing for 
  duplicates and missing atoms.  Indices of atoms are stored in the order 
  provided by the user.
    

Atom selections
-------------------------------------------------------------------------------

Flexible and powerful atom selections is one of the most important features 
of ProDy.  The details of the selection grammar is described in 
:ref:`selections`. 

.. versionadded:: 0.7.1

Using the flexibility of Python, atom selections are made much easier by
overriding the ``.`` operator i.e. the :meth:`__getattribute__` 
method of :class:`Atomic` class.  So the following will be interpreted
as atom selections:
    
>>> ag.chain_A # selects chain A
<Selection: "chain A" from 1aar (608 atoms; 1 coordinate sets, active set index: 0)>
>>> ag.calpha # selects alpha carbons
<Selection: "calpha" from 1aar (152 atoms; 1 coordinate sets, active set index: 0)>
>>> ag.resname_ALA # selects alanine residues
<Selection: "resname ALA" from 1aar (20 atoms; 1 coordinate sets, active set index: 0)>

It is also possible to combine selections with ``and`` and ``or`` operators:

>>> ag.chain_A_and_backbone
<Selection: "chain A and backbone" from 1aar (304 atoms; 1 coordinate sets, active set index: 0)>
>>> ag.acidic_or_basic
<Selection: "acidic or basic" from 1aar (422 atoms; 1 coordinate sets, active set index: 0)>


Using dot operator will behave like the logical ``and`` operator:
    
>>> ag.chain_A.backbone
<Selection: "(backbone) and (chain A)" from 1aar (304 atoms; 1 coordinate sets, active set index: 0)>
  
For this to work, the first word following the dot operator must be a selection
keyword, e.g. ``resname``, ``name``, ``apolar``, ``protein``, etc. 
Underscores will be interpreted as white space, as obvious from the
previous examples.  The limitation of this is that parentheses, special 
characters cannot be used.     

"""

__author__ = 'Ahmet Bakan'
__copyright__ = 'Copyright (C) 2010-2012 Ahmet Bakan'

from collections import defaultdict
from types import NoneType
import sys
import time

if sys.version_info[:2] < (2,7):
    from ordereddict import OrderedDict
else:
    from collections import OrderedDict

import numpy as np

from tools import *
import prody
LOGGER = prody.LOGGER

__all__ = ['Atomic', 'AtomGroup', 'AtomPointer', 'Atom', 'AtomSubset', 
           'Selection', 'Chain',
           'Residue', 'AtomMap', 'HierView', 'ATOMIC_DATA_FIELDS',
           'loadAtoms', 'saveAtoms',]

class Field(object):
    __slots__ = ['_name', '_var', '_dtype',  '_doc', '_doc_pl', 
                 '_meth', '_meth_pl', '_ndim', '_none', '_selstr',
                 '_depr', '_depr_pl', '_synonym']
    def __init__(self, name, dtype, **kwargs):
        self._name = name
        self._dtype = dtype
        self._var = kwargs.get('var', name + 's')
        self._doc = kwargs.get('doc', name)
        self._ndim = kwargs.get('ndim', 1)
        self._meth = kwargs.get('meth', name.capitalize())
        self._doc_pl = kwargs.get('doc_pl', self._doc + 's')
        self._meth_pl = kwargs.get('meth_pl', self._meth + 's')
        self._none = kwargs.get('none')
        self._selstr = kwargs.get('selstr')
        self._depr = kwargs.get('depr')
        if self._depr is None:
            self._depr_pl = None
        else:
            self._depr_pl = kwargs.get('depr_pl', self._depr + 's')
        self._synonym = kwargs.get('synonym')
        
    def name(self):
        return self._name
    name = property(name, doc='Data field name used in atom selections.')
    def var(self):
        return self._var
    var = property(var, doc='Internal variable name.')
    def dtype(self):
        return self._dtype
    dtype = property(dtype, doc='Data type (primitive Python types).')
    def doc(self):
        return self._doc
    doc = property(doc, doc='Data field name, as used in documentation.')
    def doc_pl(self):
        return self._doc_pl
    doc_pl = property(doc_pl, doc='Plural form for documentation.')
    def meth(self):
        return self._meth
    meth = property(meth, doc='Atomic get/set method name.')
    def meth_pl(self):
        return self._meth_pl
    meth_pl = property(meth_pl, doc='get/set method name in plural form.')
    def ndim(self):
        return self._ndim
    ndim = property(ndim, doc='Expected number of data array dimensions.')
    def none(self):
        return self._none
    none = property(none, doc='When to set the value of the variable to None.')
    def selstr(self):
        return self._selstr
    selstr = property(selstr, doc='Selection string examples.')
    def synonym(self):
        return self._synonym
    synonym = property(synonym, doc='Synonym used in atom selections.')
    def depr(self):
        return self._depr
    depr = property(depr, doc='Deprecated method name.')
    def depr_pl(self):
        return self._depr_pl
    depr_pl = property(depr_pl, doc='Deprecated method name in plural form.')
    def getDocstr(self, meth, plural=True, selex=True):
        """Return documentation string for the field."""
        
        assert meth in ('set', 'get', '_get'), "meth must be 'set' or 'get'"
        assert isinstance(plural, bool), 'plural must be a boolean'
        assert isinstance(selex, bool), 'selex must be a boolean'
        
        if meth == 'get':
            if plural:
                docstr = 'Return a copy of {0:s}.'.format(self.doc_pl)
            else:
                docstr = 'Return {0:s} of the atom.'.format(self.doc)
        elif meth == 'set':
            if plural:
                docstr = 'Set {0:s}.'.format(self.doc_pl)
            else:
                docstr = 'Set {0:s} of the atom.'.format(self.doc)
        else:
            selex = False
            if plural:
                docstr = 'Return {0:s} array.'.format(self.doc_pl) 
            
        selstr = self.selstr
        if selex and selstr:
            if plural:
                doc = self.doc_pl
            else:
                doc = self.doc
            if '(' in doc:
                doc = doc[:doc.index('(')]
            selex = "'``, ``'".join(selstr)
            selex = ("  {0:s} can be used in atom selections, e.g. "
                     "``'{1:s}'``.").format(doc.capitalize(), selex)
            if self.synonym is not None:
                selex = selex + ('  Note that *{0:s}* is a synonym for '
                    '*{1:s}*.').format(self.synonym, self.name)
            return docstr + selex
        else:
            return docstr

ATOMIC_DATA_FIELDS = {
    'name':      Field('name', '|S6', selstr=('name CA CB',), depr='AtomName'),
    'altloc':    Field('altloc', '|S1', doc='alternate location indicator', 
                       selstr=('altloc A B', 'altloc _'), 
                       depr='AltLocIndicator'),
    'anisou':    Field('anisou', float, doc='anisotropic temperature factor', 
                       ndim=2, depr='AnisoTempFactor'),
    'chain':     Field('chain', '|S1', var='chids', doc='chain identifier', 
                       meth='Chid', none='hv', synonym='chid', 
                       selstr=('chain A', 'chid A B C', 'chain _'), 
                       depr='ChainIdentifier'),
    'element':   Field('element', '|S2', doc='element symbol', 
                       selstr=('element C O N',), depr='ElementSymbol'),
    'hetero':    Field('hetero', bool, doc='hetero flag', 
                       selstr=('hetero', 'hetero and not water'), 
                       depr='HeteroFlag'),
    'occupancy': Field('occupancy', float, var='occupancies', 
                       doc='occupancy value', meth_pl='Occupancies',
                       selstr=('occupancy 1', 'occupancy > 0')),
    'resname':   Field('resname', '|S6', doc='residue name', 
                       selstr=('resname ALA GLY',), depr='ResidueName'),
    'resnum':    Field('resnum', int, doc='residue number', none='hv',
                       selstr=('resnum 1 2 3', 'resnum 120A 120B', 
                               'resnum 10 to 20', 'resnum 10:20:2', 
                               'resnum < 10'), synonym='resid',
                       depr='ResidueNumber'),
    'secondary': Field('secondary', '|S1', doc='secondary structure '
                       'assignment', meth='Secstr', synonym='secstr',
                       selstr=('secondary H E', 'secstr H E'),  
                       depr='SecondaryStr'),
    'segment':   Field('segment', '|S6', doc='segment name', meth='Segname',
                       selstr=('segment PROT', 'segname PROT'), 
                       synonym='segname', depr='SegmentName'),
    'siguij':    Field('siguij', float, doc='standard deviations for '
                       'anisotropic temperature factor', meth='Anistd', ndim=2, 
                       depr='AnisoStdDev'),
    'serial':    Field('serial', int, doc='serial number (from file)', 
                       doc_pl='serial numbers (from file)', none='sn2i', 
                       selstr=('serial 1 2 3', 'serial 1 to 10', 
                       'serial 1:10:2', 'serial < 10'), depr='SerialNumber'),
    'beta':      Field('beta', float, doc='β-value (temperature factor)', 
                       doc_pl='β-values (or temperature factors)', 
                       selstr=('beta 555.55', 'beta 0 to 500', 'beta 0:500', 
                       'beta < 500'), depr='TempFactor'),
    'icode':     Field('icode', '|S1', doc='insertion code', none='hv', 
                       selstr=('icode A', 'icode _'), depr='InsertionCode'),
    'type':      Field('type', '|S6', selstr=('type CT1 CT2 CT3',), 
                       depr='AtomType'),
    'charge':    Field('charge', float, doc='partial charge',  
                       selstr=('charge 1', 'abs(charge) == 1', 'charge < 0')),
    'mass':      Field('mass', float, var='masses', doc_pl='masses', 
                       meth_pl='Masses', selstr=('12 <= mass <= 13.5',)),
    'radius':    Field('radius', float, var='radii', doc='radius',  
                       doc_pl='radii', meth_pl='Radii', 
                       selstr=('radii < 1.5', 'radii ** 2 < 2.3')),
}

ATOMIC_ATTRIBUTES = {}
for field in ATOMIC_DATA_FIELDS.values():
    ATOMIC_ATTRIBUTES[field.var] = field

def wrapGetMethod(fn):
    def getMethod(self):
        return fn(self)
    return getMethod
def wrapSetMethod(fn):
    def setMethod(self, data):
        return fn(self, data)
    return setMethod

__doc__ += """

Common methods
-------------------------------------------------------------------------------

Atomic data contained in a PDB file can be accessed and changed using ``get`` 
and ``set`` methods defined for :class:`Atomic` classes.  To provide a coherent
interface, these methods are defined for :class:`AtomGroup`, :class:`Atom`, 
:class:`Selection`, :class:`Chain`, :class:`Residue`, and :class:`AtomMap` 
classes, with the following exceptions: 

* Names of methods of the :class:`Atom` class are in singular form.
* ``set`` methods are not defined for the :class:`AtomMap` class.

The list of methods are below (they link to the documentation of the 
:class:`AtomGroup` methods):
 
======================  =======================================================
Get/set method          Description
======================  =======================================================
``get/setCoords``       get/set coordinates of atoms
"""

keys = ATOMIC_DATA_FIELDS.keys()
keys.sort()

for key in keys:
    field = ATOMIC_DATA_FIELDS[key]
    __doc__ += '``get/set{0:13s}  get/set {1:s}\n'.format(field.meth_pl+'``', 
                                                          field.doc_pl)

__doc__ += """
======================  =======================================================

.. note:: Note that ``get`` methods return a copy of the data. Changes in the 
   array obtained by calling one of the above methods will not be saved in the
   :class:`AtomGroup` instance. To change the data stored in :class:`AtomGroup`
   instance, use ``set`` methods.

Other functions common to all atomic classes is given below:

=================  ==========================================================
Method name        Description
=================  ==========================================================
``copy``           returns a deep copy of atomic data
``select``         selects a subset of atoms (see :ref:`selections`)
``numAtoms``       returns number of atoms
``numCoordsets``   returns number of coordinate sets
``getCoordsets``   returns specified coordinate sets
``getACSIndex``    returns the index of the active coordinate set
``setACSIndex``    changes the index of the active coordinate set
``getACSLabel``    returns the label of the active coordinate set
``setACSLabel``    changes the label of the active coordinate set
``iterCoordsets``  iterate over coordinate sets
``isData``         checks whether a user set attribute exists
``getData``        returns user set attribute data
``setData``        changes user set attribute data
=================  ==========================================================


Special methods
-------------------------------------------------------------------------------

Atomic classes also have the following class specific methods: 
    
======================  =======================================================
Method                  Description
======================  =======================================================
:class:`AtomGroup`  
* ``getTitle``          returns title of the atom group
* ``setTitle``          changes title of the atom group
* ``delData``           deletes a user data from the atom group
* ``addCoordset``       add a coordinate set to the atom group
* ``numChains``         returns the number of chains
* ``numResidues``       returns the total number of residues from all chains
* ``iterChains``        iterates over chains
* ``iterResidues``      iterates over all residues

                      
:class:`Atom`              
* ``getIndex``          returns atom index
* ``getName``           return atom name
* ``getSelstr``         returns string that selects the atom
                    
:class:`Selection`         
* ``getIndices``        returns indices of atoms
* ``getSelstr``         returns selection string that reproduces the selection

:class:`Chain`
* ``getIdentifier``     returns chain identifier
* ``setIdentifier``     changes chain identifier
* ``getResidue``        returns residue with given number
* ``iterResidues``      iterates over residues
* ``numResidues``       returns the number of residues in the instance
* ``getSequence``       returns single letter amino acid sequence
* ``getSelstr``         returns a string that selects chain atoms
                      
:class:`Residue`
* ``getIndices``        returns indices of atoms
* ``getAtom``           returns :class:`Atom` with given name
* ``getChain``          returns :class:`Chain` of the residue
* ``getChid``           returns chain identifier
* ``getIcode``          returns residue insertion code
* ``setIcode``          changes residue insertion code 
* ``getName``           returns residue name
* ``setName``           changes residue name
* ``getNumber``         returns residue number
* ``setNumber``         changes residue number
* ``getSelstr``         returns a string that selects residue atoms

:class:`AtomMap`
* ``getIndices``        returns indices of atoms
* ``getTitle``          returns name of the atom map
* ``setTitle``          changes name of the atom map
* ``numMapped``         returns number of mapped atoms
* ``numUnmapped``       returns number of unmapped atoms
* ``getMapping``        returns mapping of indices
* ``getMappedFlags``    returns an boolean array indicating mapped atoms
* ``getUnmappedFlags``  returns an boolean array indicating unmapped atoms
======================  =======================================================

Functions common to :class:`Atom`, :class:`Selection`, :class:`Chain`,
:class:`Residue`, and :class:`AtomMap` include: 
    
======================  =======================================================
Method                  Description
======================  =======================================================
* ``getAtomGroup``      returns the associated :class:`AtomGroup`
* ``getIndices``        returns the indices of atoms
======================  =======================================================


Behavioral differences
-------------------------------------------------------------------------------

Atomic classes behave differently to indexing and to calls of certain built-in 
functions.  These differences are:

=========  ====================================================================
Class               Properties and differences
=========  ====================================================================
AtomGroup  * :func:`len` returns the number of atoms.
           * :func:`iter` yields :class:`Atom` instances.
           * Indexing by:
               
             - *atom index* (:func:`int`), e.g, ``10`` returns an 
               :class:`Atom`.
             - *slice* (:func:`slice`), e.g, ``10:20:2`` returns a 
               :class:`Selection`.
             - *chain identifier* (:func:`str`), e.g. ``"A"`` return 
               a :class:`Chain`.
             - *chain identifier, residue number [, insertion code]* 
               (:func:`tuple`), e.g. ``"A", 10`` or  ``"A", 10, "B"`` 
               returns a :class:`Residue`.
                       
Atom       * :func:`len` returns 1.
           * :func:`iter` is not applicable.
           * Indexing is not applicable.
                      
Selection  * :func:`len` returns the number of selected atoms.
           * :func:`iter` yields :class:`Atom` instances.
           * Indexing is not available.

Chain      * :func:`len` returns the number of residues in the chain.
           * :func:`iter` yields :class:`Residue` instances.
           * Indexing by:
                
             - *residue number [, insertion code]* (:func:`tuple`), 
               e.g. ``10`` or  ``10, "B"`` returns a :class:`Residue`.
                    
Residue    * :func:`len` returns the number of atoms in the instance.
           * :func:`iter` yields :class:`Atom` instances.
           * Indexing by:
              
             - *atom name* (:func:`str`), e.g. ``"CA"`` returns 
               an :class:`Atom`.

AtomMap    * :func:`len` returns the number of atoms in the instance.
           * :func:`iter` yields :class:`Atom` instances.
           * Indexing is not available.
=========  ====================================================================


Hierarchical views
-------------------------------------------------------------------------------

:class:`HierView` instances can be built for :class:`AtomGroup` and 
:class:`Selection` instances.

Some overridden functions are:

* :func:`len` return the number of chains.
* :func:`iter()` iterates over chains.
* Indexing:
    
  - *chain identifier* (:func:`str`), e.g. ``"A"`` returns a :class:`Chain`.
  - *chain identifier, residue number [, insertion code]* 
    (:func:`tuple`), e.g. ``"A", 10`` or  ``"A", 10, "B"`` 
    returns a :class:`Residue`


"""

__doc__ += """

:mod:`prody.atomic`
===============================================================================

Classes
-------

    * :class:`AtomGroup`
    * :class:`Atom`
    * :class:`Chain`
    * :class:`Residue`
    * :class:`Selection`
    * :class:`AtomMap`
    * :class:`HierView`
    
Base Classes
------------

    * :class:`Atomic`
    * :class:`AtomPointer`
    * :class:`AtomSubset`


Functions
---------

    * :func:`saveAtoms`
    * :func:`loadAtoms`

Inheritance Diagram
-------------------

.. inheritance-diagram:: prody.atomic
   :parts: 1

"""

class Atomic(object):
    
    """Base class for all atomic classes.
    
    Derived classes are:
        
      * :class:`AtomGroup`
      * :class:`AtomPointer`"""
      
    __slots__ = ['_acsi']
    
    def __contains__(self, item):
        """.. versionadded:: 0.5.3"""
        
        if isinstance(item, Atomic):
            if isinstance(item, AtomGroup) and self == item: 
                return True
            elif isinstance(self, AtomGroup) and self == item.getAtomGroup():
                return True
            elif len(item) <= len(self):
                if set(item.getIndices()).issubset(set(self.getIndices())):
                    return True
        return False        
      
    def __eq__(self, other):
        """
        .. versionadded:: 0.5.3
        
        .. versionchanged:: 0.8.1
           A :class:`Selection` (:class:`AtomPointer`) of all atoms is 
           considered not equal to the :class:`AtomGroup` anymore as 
           this causes problems in :mod:`select` module."""
        
        if isinstance(other, Atomic):
            # AtomMaps may need special handling
            if self is other:
                return True
            elif isinstance(self, AtomPointer) and \
                isinstance(other, AtomPointer):
                self_indices = self._indices
                if len(self_indices) == len(other):
                    other_indices = other.getIndices()
                    if np.all(self_indices == other_indices):
                        return True
        return False
    
    def __ne__(self, other):
        """.. versionadded:: 0.5.3"""
        
        return not self.__eq__(other)
      
    def __getattribute__(self, name):
        """.. versionadded:: 0.7.1"""
        
        try:
            return object.__getattribute__(self, name)
        except AttributeError:
            selstr = name
            items = name.split('_')
            if prody.select.isKeyword(items[0]) or items[0] == 'not' or \
               items[0] in prody.select.MACROS:
                selstr = ' '.join(items)
                return prody.ProDyAtomSelect.select(self, selstr)
        raise AttributeError("'{0:s}' object has no attribute '{1:s}' "
                             "and '{2:s}' is not a valid selection string"
                             .format(self.__class__.__name__, name, selstr))
    
    def getActiveCoordsetIndex(self):
        """Deprecated, use :meth:`getACSIndex`."""
        
        prody.deprecate('getActiveCoordsetIndex', 'getACSIndex')
        return self.getACSIndex()
    
    def getACSIndex(self):
        """Return index of the active coordinate set."""
        
        return self._acsi
    
    def select(self, selstr, **kwargs):
        """Return atoms matching the criteria in *selstr*.
        
        .. seealso:: :meth:`~prody.select.Select.select()` for more usage 
           details."""
        
        return prody.ProDyAtomSelect.select(self, selstr, **kwargs)


class AtomGroupMeta(type):

    def __init__(cls, name, bases, dict):
    
        for field in ATOMIC_DATA_FIELDS.values():

            meth = field.meth_pl
            getMeth = 'get' + meth
            setMeth = 'set' + meth
            # Define public method for retrieving a copy of data array
            def getData(self, var=field.var):
                array = self._data[var]
                if array is None:
                    return None
                return array.copy() 
            getData = wrapGetMethod(getData)
            getData.__name__ = getMeth
            getData.__doc__ = field.getDocstr('get')
            setattr(cls, getMeth, getData)
            
            # Define private method for retrieving actual data array
            def _getData(self, var=field.var):
                return self._data[var]
            _getData = wrapGetMethod(_getData)
            _getData.__name__ = '_' + getMeth
            _getData.__doc__ = field.getDocstr('_get')
            setattr(cls, '_' + getMeth, _getData)
            
            # Define public method for setting values in data array
            def setData(self, array, var=field.var, dtype=field.dtype, 
                        ndim=field.ndim, none=field.none):
                if self._n_atoms == 0:
                    self._n_atoms = len(array)
                elif len(array) != self._n_atoms:
                    raise ValueError('length of array must match numAtoms')
                    
                if isinstance(array, list):
                    array = np.array(array, dtype)
                elif not isinstance(array, np.ndarray):
                    raise TypeError('array must be an ndarray or a list')
                elif array.ndim != ndim:
                        raise ValueError('array must be {0:d} dimensional'
                                         .format(ndim))
                elif array.dtype != dtype:
                    try:
                        array = array.astype(dtype)
                    except ValueError:
                        raise ValueError('array cannot be assigned type '
                                         '{0:s}'.format(dtype))
                self._data[var] = array
                if none:
                    self.__setattr__('_'+none,  None)
            setData = wrapSetMethod(setData)
            setData.__name__ = setMeth 
            setData.__doc__ = field.getDocstr('set')
            setattr(cls, setMeth, setData)
            
            
            # DEPRECATIONS
            if field.depr:
                depr = field.depr_pl
                getDepr = 'get' + depr
                setDepr = 'set' + depr
                # Define public method for retrieving a copy of data array
                def getData(self, old=getDepr, new=getMeth):
                    prody.deprecate(old, new, 4)
                    return self.__getattribute__(new)() 
                getData = wrapGetMethod(getData)
                getData.__name__ = getDepr
                getData.__doc__ = 'Deprecated, use :meth:`{0:s}`'.format(getMeth)
                setattr(cls, getDepr, getData)
                
                # Define public method for setting values in data array
                def setData(self, value, old=setDepr, new=setMeth):
                    prody.deprecate(old, new, 4)
                    self.__getattribute__(new)(value) 
                setData = wrapSetMethod(setData)
                setData.__name__ = setDepr 
                setData.__doc__ = 'Deprecated, use :meth:`{0:s}`'.format(setMeth)
                setattr(cls, setDepr, setData)


class AtomGroup(Atomic):
    
    """A class for storing and accessing atomic data.
    
    The number of atoms of the atom group is inferred at the first set method
    call from the size of the data array. 

    **Atomic Data**
    
    All atomic data is stored in :class:`numpy.ndarray` instances.

    **Get and Set Methods**
    
    :meth:`get` methods return copies of the data arrays. 
    
    :meth:`set` methods accept data in :class:`list` or :class:`~numpy.ndarray` 
    instances. The length of the list or array must match the number of atoms 
    in the atom group. Set method sets attributes of all atoms at once.
    
    Atom groups with multiple coordinate sets may have one of these sets as 
    the active coordinate set. The active coordinate set may be changed using
    :meth:`setACSIndex()` method.  :meth:`getCoors` returns coordinates from 
    the active set.
    
    To access and modify data associated with a subset of atoms in an atom 
    group, :class:`Selection` instances may be used. A selection from an atom 
    group has initially the same coordinate set as the active coordinate set.
    
    User can iterate over atoms and coordinate sets in an atom group. To 
    iterate over residues and chains, get a hierarchical view of the atom 
    group by calling :meth:`getHierView()`.
    
    """
    
    __metaclass__ = AtomGroupMeta
    
    __slots__ = ['_acsi', '_title', '_n_atoms', '_coordinates', '_n_csets',
                 '_cslabels', 
                 '_hv', '_sn2i',
                 '_trajectory', '_frameindex', '_tcsi', '_timestamps',
                 '_data']
    
    def __init__(self, title='Unnamed'):
        """Instantiate an AtomGroup with a *title*."""
        
        self._title = str(title)
        self._n_atoms = 0
        self._coordinates = None
        self._cslabels = []
        self._acsi = None                  # Active Coordinate Set Index
        self._n_csets = 0
        self._hv = None
        self._sn2i = None
        self._trajectory = None
        self._frameindex = None
        self._tcsi = None # Trajectory Coordinate Set Index
        self._timestamps = None
        self._data = dict()
        
        for field in ATOMIC_DATA_FIELDS.values():
            self._data[field.var] = None

    def _getTimeStamp(self, index):
        """Return time stamp showing when coordinates were last changed."""

        if self._n_csets > 0:
            if index is None:
                return self._timestamps[self._acsi]
            else:
                return self._timestamps[index]
        else:
            return None
    
    def _setTimeStamp(self, index=None):
        """Set time stamp when:
           
            * :meth:`setCoordinates` method of :class:`AtomGroup` or 
              :class:`AtomPointer` instances are called.
              
            * one of :meth:`nextFrame`, or :meth:`gotoFrame` methods is called.
        """
        
        if index is None:
            self._timestamps = np.zeros(self._n_csets)
            self._timestamps[:] = time.time()
        else:
            self._timestamps[index] = time.time()

    def __repr__(self):
        if self._trajectory is None:
            if self._n_csets > 0:
                return ('<AtomGroup: {0:s} ({1:d} atoms; {2:d} coordinate '
                        'sets, active set index: {3:d})>').format(self._title, 
                                    self._n_atoms, self._n_csets, self._acsi)
            else:
                return ('<AtomGroup: {0:s} ({1:d} atoms; {2:d} coordinate '
                        'sets)>').format(self._title,  self._n_atoms, 
                        self._n_csets)
        else:
            return ('<AtomGroup: {0:s} ({1:d} atoms; trajectory {2:s}, '
                    'frame index {3:d})>').format(self._title, 
                    self._n_atoms, self._trajectory.getTitle(), self._tcsi, 
                    len(self._trajectory))
        
    def __str__(self):
        return ('AtomGroup {0:s}').format(self._title)
        return ('{0:s} ({1:d} atoms; {2:d} coordinate sets, active '
               'set index: {3:d})').format(self._title, 
              self._n_atoms, self._n_csets, self._acsi)

    def __getitem__(self, indices):
        acsi = self._acsi
        if isinstance(indices, int):
            if indices < 0:
                indices = self._n_atoms + indices
            return Atom(self, indices, acsi)
        elif isinstance(indices, slice):
            start, stop, step = indices.indices(self._n_atoms)
            if start is None:
                start = 0
            if step is None:
                step = 1
            selstr = 'index {0:d}:{1:d}:{2:d}'.format(start, stop, step)
            return Selection(self, np.arange(start,stop,step), selstr, acsi)
        elif isinstance(indices, (list, np.ndarray)):
            return Selection(self, np.array(indices), 'Some atoms', 
                 'index {0:s}'.format(' '.join(np.array(indices, '|S'))), acsi)
        elif isinstance(indices, (str, tuple)):
            hv = self.getHierView()
            return hv[indices]
        else:
            raise TypeError('invalid index') 
    
    def __iter__(self):
        """Iterate over atoms in the atom group."""
        
        acsi = self._acsi
        for index in xrange(self._n_atoms):
            yield Atom(self, index, acsi)

    def __len__(self):
        return self._n_atoms
    
    def __add__(self, other):
        """.. versionadded:: 0.5"""
        
        if isinstance(other, AtomGroup):
            if self == other:
                raise ValueError('an atom group cannot be added to itself')
            
            new = AtomGroup(self._title + ' + ' + other._title)
            n_coordsets = self._n_csets
            if n_coordsets != other._n_csets:
                LOGGER.warning('AtomGroups {0:s} and {1:s} do not have same '
                               'number of coordinate sets.  First from both '
                               'AtomGroups will be merged.'
                  .format(str(self._title), str(other._title), n_coordsets))
                n_coordsets = 1
            coordset_range = range(n_coordsets)
            new.setCoords(np.concatenate((self._coordinates[coordset_range],
                                        other._coordinates[coordset_range]), 1))
            for field in ATOMIC_DATA_FIELDS.values():
                var = field.var
                this = self._data[var]
                that = other._data[var]
                if this is not None and that is not None:
                    new._data[var] = np.concatenate((this, that))
            return new
        elif isinstance(other, prody.VectorBase):
            if self._n_atoms != other.numAtoms(): 
                raise ValueError('Vector/Mode must have same number of atoms '
                                 'as the AtomGroup')
            self.addCoordset(self._coordinates[self._acsi] + 
                             other._getArrayNx3())
            self.setACSIndex(self._n_csets - 1)
        else:
            raise TypeError('can only concatenate two AtomGroup`s or can '
                            'deform AtomGroup along a Vector/Mode')

    def _buildSN2I(self):
        """Builds a mapping from serial numbers to atom indices."""
        
        serials = self._serials  
        if serials is None:
            raise AttributeError('atom serial numbers are not set')
        if len(np.unique(serials)) != self._n_atoms:
            raise ValueError('atom serial numbers must be unique')
        if serials.min() < 0:
            raise ValueError('atoms must not have negative serial numbers')
        sn2i = -np.ones(serials.max() + 1)
        sn2i[serials] = np.arange(self._n_atoms)
        self._sn2i = sn2i

    def _getSN2I(self):
        if self._sn2i is None:
            self._buildSN2I()
        return self._sn2i

    def getName(self):
        """Deprecated, use :meth:`getTitle`."""

        prody.deprecate('getName', 'getTitle')
        return self.getTitle()
        
    def getTitle(self):
        """Return title of the atom group instance."""
        
        return self._title
    
    def setName(self, name):
        """Deprecated, use :meth:`setTitle`."""

        prody.deprecate('setName', 'setTitle')
        return self.setTitle(name)
        
    def setTitle(self, title):
        """Set title of the atom group instance."""
        
        self._title = str(title)
    
    def getNumOfAtoms(self):
        """Deprecated, use :meth:`numAtoms`."""

        prody.deprecate('getNumOfAtoms', 'numAtoms')
        return self.numAtoms()
        
    def numAtoms(self):
        """Return number of atoms."""
        
        return self._n_atoms
    
    def getCoordinates(self):
        """Deprecated, use :meth:`getCoords`."""
        
        prody.deprecate('getCoordinates', 'getCoords')
        return self.getCoords()
        
    def getCoords(self):
        """Return a copy of coordinates from active coordinate set."""
        
        if self._coordinates is None:
            return None
        return self._coordinates[self._acsi].copy()
    
    def _getCoords(self): 
        """Return a view of coordinates from active coordinate set."""
        
        if self._coordinates is None:
            return None
        return self._coordinates[self._acsi]

    def setCoordinates(self, coordinates):
        """Deprecated, use :meth:`setCoords`."""
        
        prody.deprecate('setCoordinates', 'setCoords')
        return self.setCoords(coordinates)
        
    def setCoords(self, coords, label=None):
        """Set coordinates.  *coords* must be a :class:`numpy.ndarray` 
        instance.  If the shape of the coordinates array is 
        (n_csets,n_atoms,3), the given array will replace all coordinate sets. 
        To avoid it, :meth:`addCoordset` may be used.  If the shape of the 
        coordinates array is (n_atoms,3) or (1,n_atoms,3), the coordinate set 
        will replace the coordinates of the currently active coordinate set.
        
        .. versionadded:: 0.9.3
           *label* argument is added to allow labeling coordinate sets.  
           *label* may be a string or a list of strings length equal to the
           number of coordinate sets."""

        coordinates = checkCoords(coords, 'coords',
                                  cset=True, n_atoms=self._n_atoms,
                                  reshape=True)
        if self._n_atoms == 0:
            self._n_atoms = coordinates.shape[-2] 
        acsi = None
        if self._coordinates is None:
            self._coordinates = coordinates
            self._n_csets = coordinates.shape[0]
            self._acsi = 0
            self._setTimeStamp()
            if isinstance(label, (NoneType, str)):
                self._cslabels = [label] * self._n_csets
            elif isinstance(label, (list, tuple)):
                if len(label) == self._n_csets:
                    self._cslabels = label
                else:
                    self._cslabels = [None] * self._n_csets
                    LOGGER.warning('Length of `label` does not match number '
                                   'of coordinate sets.')
                
        else:
            if coordinates.shape[0] == 1:
                acsi = self._acsi
                self._coordinates[acsi] = coordinates[0]
                self._setTimeStamp(acsi)
                if isinstance(label, str):
                    self._cslabels[self._acsi] = label
            else:
                self._coordinates = coordinates
                self._n_csets = coordinates.shape[0]
                self._acsi = min(self._n_csets - 1, self._acsi)
                self._setTimeStamp()
        if acsi is None:
            if isinstance(label, (str, NoneType)):
                self._cslabels = [label] * self._n_csets
            elif isinstance(label, (list, tuple)):
                if len(label) == self._n_csets:
                    if all([isinstance(lbl, str) for lbl in label]):
                        self._cslabels += label
                    else:
                        LOGGER.warning('all items of `label` must be strings')
                else:
                    LOGGER.warning('`label` must have same length as the '
                                   '`coords` array')
            else:
                LOGGER.warning('`label` must be a string or list of strings')
        elif label is not None:
            if isinstance(label, str):
                self._cslabels[acsi] = label
            elif isinstance(label, (list, tuple)):
                if len(label) == 1:
                    if isinstance(label[0], str):
                        self._cslabels[acsi] = label
                    else:
                        LOGGER.warning('all items of `label` must be strings')
                else:
                    LOGGER.warning('length of `label` must be one')
            else:
                LOGGER.warning('`label` must be a string or list of strings')
                    
            
    def addCoordset(self, coords, label=None):
        """Add a coordinate set to the atom group.
        
        .. versionchanged:: 0.6.2
            :class:`~prody.ensemble.Ensemble` and :class:`Atomic` instances are 
            accepted as *coords* argument."""
        
        if self._trajectory is not None:
            raise AttributeError('AtomGroup is locked for coordinate set '
                                 'addition/deletion when its associated with '
                                 'a trajectory')
        if isinstance(coords, (prody.ensemble.Ensemble, Atomic)):
            if self._n_atoms != coords.numAtoms(): 
                raise ValueError('coords must have same number of atoms')
            coords = coords.getCoordsets()

        if self._coordinates is None:
            self.setCoords(coords)
            return

        coords = checkCoords(coords, 'coords', cset=True, 
                             n_atoms=self._n_atoms, reshape=True)
        diff = coords.shape[0]
        self._coordinates = np.concatenate((self._coordinates, coords), axis=0)
        self._n_csets = self._coordinates.shape[0]
        timestamps = self._timestamps
        self._timestamps = np.zeros(self._n_csets)
        self._timestamps[:len(timestamps)] = timestamps
        self._timestamps[len(timestamps):] = time.time()
        
        if isinstance(label, (str, NoneType)):
            self._cslabels += [label] * diff
        elif isinstance(label, (list, tuple)):
            if len(label) == diff:
                if all([isinstance(lbl, str) for lbl in label]):
                    self._cslabels += label
                else:
                    LOGGER.warning('all items of `label` must be strings')
            else:
                LOGGER.warning('`label` list must have same length as the '
                               '`coords` array')
        else:
            LOGGER.warning('`label` must be a string or list of strings')
        
    def delCoordset(self, index):
        """Delete a coordinate set from the atom group."""
        
        if self._n_csets == 0:
            raise AttributeError('coordinates are not set')
        if self._trajectory is not None:
            raise AttributeError('AtomGroup is locked for coordinate set '
                                 'addition/deletion when its associated with '
                                 'a trajectory')
        which = np.ones(self._n_csets, bool)
        which[index] = False
        n_csets = self._n_csets
        which = which.nonzero()[0]
        if len(which) == 0:
            self._coordinates = None
            self._n_csets = 0
            self._acsi = None
            self._cslabels = None
        else:
            self._coordinates = self._coordinates[which]
            self._n_csets = self._coordinates.shape[0]
            self._acsi = 0
            self._cslabels = [self._cslabels[i] for i in which]
        self._timestamps = self._timestamps[which]        

    def getCoordsets(self, indices=None):
        """Return a copy of coordinate set(s) at given *indices*.  *indices* 
        may  be an integer, a list of integers, or ``None`` meaning all 
        coordinate sets."""
        
        if self._coordinates is None:
            return None
        if indices is None:
            return self._coordinates.copy()
        if isinstance(indices, (int, slice)):
            return self._coordinates[indices].copy()
        if isinstance(indices, (list, np.ndarray)):
            return self._coordinates[indices]
        raise IndexError('indices must be an integer, a list/array of '
                         'integers, a slice, or None')
        
    def _getCoordsets(self, indices=None):
        """Return a view of coordinate set(s) at given *indices*."""
        
        if self._coordinates is None:
            return None
        if indices is None:
            return self._coordinates
        if isinstance(indices, (int, slice, list, np.ndarray)):
            return self._coordinates[indices]
        raise IndexError('indices must be an integer, a list/array of '
                         'integers, a slice, or None')

    def getNumOfCoordsets(self):
        """Deprecated, use :meth:`numCoordsets`."""
        
        prody.deprecate('getNumOfCoordsets', 'numCoordsets')
        return self.numCoordsets()
        
    def numCoordsets(self):
        """Return number of coordinate sets."""
        
        return self._n_csets
    
    def iterCoordsets(self):
        """Iterate over coordinate sets by returning a copy of each coordinate
        set."""
        
        for i in range(self._n_csets):
            yield self._coordinates[i].copy()
    
    def _iterCoordsets(self):
        """Iterate over coordinate sets by returning a view of each coordinate
        set."""
        
        for i in range(self._n_csets):
            yield self._coordinates[i]

    def setActiveCoordsetIndex(self, index):
        """Deprecated, use :meth:`setACSIndex`."""
        
        prody.deprecate('setActiveCoordsetIndex', 'setACSIndex')
        return self.setACSIndex(index)
        
    def setACSIndex(self, index):
        """Set the index of the active coordinate set."""
        
        if self._n_csets == 0:
            self._acsi = 0
        if not isinstance(index, int):
            raise TypeError('index must be an integer')
        if self._n_csets <= index or self._n_csets < abs(index):
            raise IndexError('coordinate set index is out of range')
        if index < 0:
            index += self._n_csets 
        self._acsi = index

    def copy(self, which=None):
        """Return a copy of atoms indicated *which* as a new AtomGroup 
        instance.
        
        *which* may be:
            * ``None``, make a copy of the AtomGroup
            * a Selection, Residue, Chain, or Atom instance
            * a list or an array of indices
            * a selection string
            
        .. versionchanged:: 0.7.1
           If selection string does not select any atoms, ``None`` is returned.
        
        .. versionchanged:: 0.8
           User data stored in the atom group is also copied.
           
        .. versionchanged:: 0.9.2
           Copy AtomGroup title does not start with 'Copy of'.
        
        Note that association of an atom group with a trajectory is not copied.
        """
        
        title = self._title
        if which is None:
            indices = None
            newmol = AtomGroup('{0:s}'.format(title))
            newmol.setCoords(self._coordinates.copy())
        elif isinstance(which, int):
            indices = [which]
            newmol = AtomGroup('{0:s} index {1:d}'.format(title, which))
        elif isinstance(which, str):
            indices = prody.ProDyAtomSelect.getIndices(self, which)
            if len(indices) == 0:
                return None
            newmol = AtomGroup('{0:s} selection "{1:s}"'
                               .format(title, which))
        elif isinstance(which, (list, np.ndarray)):
            if isinstance(which, list):
                indices = np.array(which)
            elif which.ndim != 1:
                raise ValueError('which must be a 1d array')
            else:
                indices = which
            newmol = AtomGroup('{0:s} subset'.format(title))
        else:
            if isinstance(which, Atom):
                indices = [which.getIndex()]
            elif isinstance(which, (AtomSubset, AtomMap)):
                indices = which.getIndices()
            else:
                raise TypeError('{0:s} is not a valid type'.format(
                                                                type(which)))            
            newmol = AtomGroup('{0:s} selection "{1:s}"'.format(title, 
                                                                str(which)))
        if indices is not None:
            newmol.setCoords(self._coordinates[:, indices])
        for key, array in self._data.iteritems():
            if array is not None:
                if indices is None:
                    newmol._data[key] = array.copy()
                else:
                    newmol._data[key] = array[indices]
        return newmol
    
    def getHierView(self):
        """Return a hierarchical view of the atom group."""
        
        hv = self._hv
        if hv is None:
            hv = HierView(self)
            self._hv = hv
        return hv
    
    def getNumOfChains(self):
        """Deprecated, use :meth:`numChains`."""
        
        prody.deprecate('getNumOfChains', 'numChains')
        return self.numChains()
    
    def numChains(self):
        """Return number of chains.
        
        .. versionadded:: 0.7.1"""
        
        return self.getHierView().numChains()
    
    def iterChains(self):
        """Iterate over chains.
        
        .. versionadded:: 0.7.1"""
        
        return self.getHierView().iterChains()
    
    def getNumOfResidues(self):
        """Deprecated, use :meth:`numResidues`."""
        
        prody.deprecate('getNumOfResidues', 'numResidues')
        return self.numResidues()
        
    def numResidues(self):
        """Return number of residues.
        
        .. versionadded:: 0.7.1"""
        
        return self.getHierView().numResidues()

    def iterResidues(self):
        """Iterate over residues.
        
        .. versionadded:: 0.7.1"""
        
        return self.getHierView().iterResidues()


    def getAttrNames(self):
        """Deprecated, use :meth:`getDataLabels`."""
        
        prody.deprecate('getAttrNames', 'getDataLabels')
        return self.getDataLabels()

    def getDataLabels(self):
        """Return list of user data labels.
        
        .. versionadded:: 0.8"""
        
        return [key for key, data in self._data.iteritems() 
                    if data is not None]
        
    def getAttrType(self, name):
        """Deprecated, use :meth:`getDataType`."""
        
        prody.deprecate('getAttrType', 'getDataType')
        return self.getDataType(name)
        
    def getDataType(self, label):
        """Return type of the user data (i.e. data.dtype) associated with
        *label*, or ``None`` label is not used.
        
        .. versionadded:: 0.9"""
        
        try:
            return self._data[label].dtype
        except KeyError:
            return None

    def setAttribute(self, name, data):
        """Deprecated, use :meth:`setData`."""
        
        prody.deprecate('setAttribute', 'setData')
        return self.setData(name, data)
        
    def setData(self, label, data):
        """Store atomic *data* under *label*.
        
        .. versionadded:: 0.7.1
        
        *label* must:
            
            * start with a letter
            * contain only alphanumeric characters and underscore
            * not be a reserved word 
              (see :func:`~prody.select.getReservedWords`)

        *data* must be a :func:`list` or a :class:`numpy.ndarray`, its length 
        must be equal to the number of atoms, and the type of data array must 
        be one of:
            
            * :class:`bool`
            * :class:`float`
            * :class:`int`
            * :class:`string`
        
        If a :class:`list` is given, its type must match one of the above after 
        it is converted to an :class:`numpy.ndarray`.  If the dimension of the 
        *data* array is 1 (i.e. ``data.ndim==1``), *label* can be used to make
        atom selections, e.g. ``"label 1 to 10"`` or ``"label C1 C2"``.  Note 
        that, if data with *label* is present, it will be overridden."""
        
        if not isinstance(label, str):
            raise TypeError('label must be a string')
        if label == '':
            raise ValueError('label cannot be empty string')
        if not label[0].isalpha():
            raise ValueError('label must start with a letter')
        if not (''.join((''.join(label.split('_'))).split())).isalnum():
            raise ValueError('label may contain alphanumeric characters and '
                             'underscore, {0:s} is not valid'.format(label))
            
        if prody.select.isReserved(label):
            raise ValueError('label cannot be a reserved word or a selection '
                             'keyword, "{0:s}" is invalid'.format(label))
        if len(data) != self._n_atoms:
            raise ValueError('length of data array must match number of atoms')
        if isinstance(data, list):
            data = np.array(data)
        elif not isinstance(data, np.ndarray):
            raise TypeError('data must be a numpy.ndarray instance')
        if not data.dtype in (np.float, np.int, np.bool) and \
              data.dtype.type != np.string_:
            raise TypeError('type of data array must be float, int, or '
                            'string_, {0:s} is not valid'.format(
                            str(data.dtype)))
            
        self._data[label] = data
    
    def delAttribute(self, name):
        """Deprecated, use :meth:`delData`."""
        
        prody.deprecate('delAttribute', 'delData')
        return self.delData(name)
        
    def delData(self, label):
        """Return data associated with *label* and remove it from the atom 
        group.  If data associated with *label* is not found, ``None`` will 
        be returned.
        
        .. versionadded:: 0.7.1"""
        
        if not isinstance(label, str):
            raise TypeError('label must be a string')
        return self._data.pop(label, None)
    
    def getAttribute(self, name):
        """Deprecated, use :meth:`getData`."""
        
        prody.deprecate('getAttribute', 'getData')
        return self.getData(name)
        
    def getData(self, label):
        """Return a copy of the data array associated with *label*, or ``None`` 
        if such data is not present.
        
        .. versionadded:: 0.7.1"""
        
        data = self._data.get(label, None)
        if data is None:
            return None
        else:
            return data.copy()

    def _getData(self, label):
        """Return data array associated with *label*, or ``None`` if such data 
        is not present."""
        
        data = self._data.get(label, None)
        if data is None:
            return None
        else:
            return data

    def isAttribute(self, name):
        """Deprecated, use :meth:`isData`."""
        
        prody.deprecate('isAttribute', 'isData')
        return self.isData(name)

    def isData(self, label):
        """Return **True** if *label* is user data.
        
        .. versionadded:: 0.7.1"""
        
        return label in self._data and self._data[label] is not None
  
    def getBySerial(self, serial, stop=None, step=None):
        """Get an atom(s) by *serial* number (range).  *serial* must be zero or 
        a positive integer. *stop* may be ``None``, or an integer greater than 
        *serial*.  ``getBySerial(i, j)`` will return atoms whose serial numbers
        are i+1, i+2, ..., j-1.  Atom whose serial number is *stop* will be 
        excluded as it would be in indexing a Python :class:`list`.  *step* 
        (default is 1) specifies increment.  If atoms with matching serial 
        numbers are not found, ``None`` will be returned. 
        
        .. versionadded:: 0.8"""

        if not isinstance(serial, int):
            raise TypeError('serial must be an integer')
        if serial < 0:
            raise ValueError('serial must be greater than or equal to zero')
        sn2i = self._getSN2I()
        if stop is None:
            if serial < len(sn2i):
                index = sn2i[serial]
                if index != -1:
                    return Atom(self, index)
        else:
            if not isinstance(stop, int):
                raise TypeError('stop must be an integer')
            if stop <= serial:
                raise ValueError('stop must be greater than serial')
                
            if step is None:
                step = 1
            else:
                if not isinstance(step, int):
                    raise TypeError('step must be an integer')
                if step < 1:
                    raise ValueError('step must be greater than zero')
            
            indices = sn2i[serial:stop:step]
            indices = indices[indices > -1]
            return Selection(self, indices, 'serial {0:d}:{1:d}:{2:d}'
                                            .format(serial, stop, step))

    def getBySerialRange(self, start, stop, step=None):
        """Deprecated, use :meth:`getBySerial`."""
        
        prody.deprecate('getBySerialRange', 'getBySerial')
        return self.getBySerial(start, stop, step)


    def setTrajectory(self, trajectory):              
        """Associates atom group with a *trajectory*.  *trajectory* may be a 
        filename or a :class:`~prody.ensemble.Trajectory` instance.  Number of 
        atoms in the atom group and the trajectory must match.  At association
        a new coordinate set will be added to the atom group.  
        :meth:`nextFrame`, and :meth:`gotoFrame` methods can be used to read 
        coordinate sets from the trajectory.  To remove association with a 
        trajectory, pass ``None`` as trajectory argument.  When atom group is 
        associated with a trajectory, it will be locked for coordinate set 
        addition/deletion operations.
        
        .. versionadded:: 0.8"""
        
        if trajectory is None:
            self._tcsi = None
            self._trajectory = None
            self.delCoordset(self._acsi)
            self._cslabels.pop()
        else:
            if isinstance(trajectory, str):
                trajectory = prody.Trajectory(trajectory)
            elif not isinstance(trajectory, prody.TrajectoryBase):
                raise TypeError('trajectory must be a file name or a '
                                'TrajectoryBase instance')
            if self._n_atoms != trajectory.numAtoms():
                raise ValueError('trajectory must have same number of atoms')
            self._tcsi = trajectory.getNextIndex()
            self._cslabels.append(trajectory.getTitle())
            self.addCoordset(trajectory.nextCoordset())
            self._acsi = self._n_csets - 1
            self._trajectory = trajectory
        
    def getTrajectory(self):
        """Return trajectory associated with the atom group."""
        
        return self._trajectory
    
    def nextFrame(self, step=1):
        """Read the next frame from the trajectory and update coordinates.
        *step* can be incremented to skip frames.
        
        .. versionadded:: 0.8"""
        
        if not isinstance(step, int) or step < 1:
            raise TypeError('step must be a positive integer')
        nfi = self._trajectory.getNextIndex()
        if step > 1:
            self._trajectory.skip(step - 1)
        if nfi - self._tcsi == 1:
            self._tcsi = nfi
            self._coordinates[self._acsi] = self._trajectory.nextCoordset()
            self._setTimeStamp(self._acsi)
        else:
            self._gotoFrame(self._tcsi + step)
                
    def skipFrame(self, n=1): 
        """Deprecated, use :meth:`nextFrame`."""
        
        prody.deprecate('skipFrame', 'nextFrame')
        return self.nextFrame(n+1)
    
    def gotoFrame(self, n):
        """Read frame *n* from the trajectory and update coordinates.
        
        .. versionadded:: 0.8"""
        
        self._trajectory.goto(n)
        self._tcsi = self._trajectory.getNextIndex()
        self._coordinates[self._acsi] = self._trajectory.nextCoordset()
        self._setTimeStamp(self._acsi)
    
    def getFrameIndex(self):
        """Return current trajectory frame index, ``None`` if atoms are not
        associated with a trajectory.
        
        .. versionadded:: 0.8"""
        
        return self._tcsi
    
    def getACSLabel(self):
        """Return active coordinate set label.
        
        .. versionadded:: 0.9.3"""
        
        if self._n_csets:
            return self._cslabels[self._acsi]

    def setACSLabel(self, label):
        """Set active coordinate set label.
        
        .. versionadded:: 0.9.3"""

        if self._n_csets:
            if isinstance(label, (str, NoneType)):
                self._cslabels[self._acsi] = label 
            else:
                raise TypeError('`label` must be a string')
    
    def getCSLabels(self):
        """Return coordinate set labels.
        
        .. versionadded:: 0.9.3"""
        
        if self._n_csets:
            return list(self._cslabels)

    def setCSLabels(self, labels):
        """Set coordinate set labels. *labels* must be a list of strings.
        
        .. versionadded:: 0.9.3"""
        
        if isinstance(labels, list):
            if len(labels) == self._n_csets:
                if all(isinstance(lbl, (str, NoneType)) for lbl in labels):
                    self._cslabels = list(labels)
                else:
                    raise ValueError('all items of labels must be strings')
            else:
                raise ValueError('length of labels must be equal to number of '
                                 'coordinate sets')
        else:
            raise TypeError('labels must be a list')                

class AtomPointer(Atomic):
    
    """Base class for classes pointing to atom(s) in :class:`AtomGroup` 
    instances.
    
    Derived classes are:
        
      * :class:`Atom`
      * :class:`AtomSubset`
      * :class:`AtomMap`
      
    """
    
    def __init__(self, atomgroup, acsi=None):
        if not isinstance(atomgroup, AtomGroup):
            raise TypeError('atomgroup must be AtomGroup, not {0:s}'
                            .format(type(atomgroup)))
        self._ag = atomgroup
        if acsi is None:
            self._acsi = atomgroup.getACSIndex()
        else: 
            self._acsi = int(acsi)

    def __add__(self, other):
        """Returns an :class:`AtomMap` instance. Order of pointed atoms are
        preserved.
        
        .. versionadded:: 0.5"""
        
        if not isinstance(other, AtomPointer):
            raise TypeError('an AtomPointer instance cannot be added to a '
                            '{0:s} instance'.format(type(other)))
        ag = self._ag
        if ag != other._ag:
            raise ValueError('AtomPointer instances must point to same '
                             'AtomGroup instance')
        acsi = self._acsi
        if self._acsi != other._acsi:
            LOGGER.warning('Active coordinate set indices of operands are not '
                           'the same.  Result will have {0:d}'.format(acsi))
        
        title = '({0:s}) + ({1:s})'.format(str(self), str(other))
        indices = np.concatenate([self.getIndices(), other.getIndices()])
        length = len(self)
        if isinstance(self, AtomMap):
            mapping = [self.getMapping()]
            unmapped = [self._unmapped]
        else:
            mapping = [np.arange(length)]
            unmapped = [np.array([])]
        
        if isinstance(other, AtomMap):
            mapping.append(other.getMapping() + length)
            unmapped.append(other._unmapped + length) 
        else:
            mapping.append(np.arange(length, length+len(other)))
            unmapped.append(np.array([]))
        return AtomMap(ag, indices, np.concatenate(mapping), 
                       np.concatenate(unmapped), title, acsi)
    
    def _getTimeStamp(self, index=None):
        
        if index is None:
            return self._ag._getTimeStamp(self._acsi)
        else:
            return self._ag._getTimeStamp(index)
    
    def isAttribute(self, name):    
        """Deprecated, use :meth:`isData`."""
        
        prody.deprecate('isAttribute', 'isData')
        return self.isData(name)
        
    def isData(self, label):
        """Return ``True`` if *label* is a user data.
        
        .. versionadded:: 0.7.1"""
        
        return self._ag.isData(label)


    def getAttrType(self, name):
        """Deprecated, use :meth:`getDataType`."""
        
        prody.deprecate('getAttrType', 'getDataType')
        return self.getDataType(name)
        
    def getDataType(self, label):
        """Return type of the user data, ``None`` if data label is not present.
        
        .. versionadded:: 0.9"""
        
        return self._ag.getDataType(label)
    
    def getAtomGroup(self):
        """Return associated atom group."""
        
        return self._ag
    
    def getNumOfCoordsets(self):
        """Deprecated, use :meth:`numCoordsets`."""
        
        prody.deprecate('getNumOfCoordsets', 'numCoordsets')
        return self.numCoordsets()
        
    def numCoordsets(self):
        """Return number of coordinate sets."""
        
        return self._ag._n_csets

    def setActiveCoordsetIndex(self, index):
        """Deprecated, use :meth:`setACSIndex`."""
        
        prody.deprecate('setActiveCoordsetIndex', 'setACSIndex')
        self.setACSIndex(index)
        
    def setACSIndex(self, index):
        """Set the index of the active coordinate set."""
        
        if self._ag._coordinates is None:
            raise AttributeError('coordinates are not set')
        if not isinstance(index, int):
            raise TypeError('index must be an integer')
        if self._ag._n_csets <= index or \
           self._ag._n_csets < abs(index):
            raise IndexError('coordinate set index is out of range')
        if index < 0:
            index += self._ag._n_csets
        self._acsi = index
        
    def copy(self, selstr=None):
        """Make a copy of atoms."""
        
        if selstr is None:
            return self._ag.copy(self)
        elif isinstance(selstr, str):
            return self._ag.copy(self.select(selstr))
        raise TypeError('selstr must be a string')
        
    def nextFrame(self):
        """Read the next frame from the trajectory and update coordinates.
        
        .. versionadded:: 0.8"""
        
        self._ag.nextFrame()
                
    def skipFrame(self, n=1): 
        """Deprecated, use :meth:`nextFrame`"""
        
        prody.deprecate('skipFrame', 'nextFrame') 
        self._ag.nextFrame(n+1)
    
    def gotoFrame(self, n):
        """Read frame *n* from the trajectory and update coordinates.
        
        .. versionadded:: 0.8"""
        
        self._ag.gotoFrame(n)
    
    def getFrameIndex(self):
        """Return current frame index.
        
        .. versionadded:: 0.8"""
        
        return self._ag.getFrameIndex()
            
    def getACSLabel(self):
        """Return active coordinate set label.
        
        .. versionadded:: 0.9.3"""
        
        if self._ag._n_csets:
            return self._ag._cslabels[self._acsi]

class AtomMeta(type):

    def __init__(cls, name, bases, dict):
        
        for field in ATOMIC_DATA_FIELDS.values():
            
            meth = field.meth
            getMeth = 'get' + meth
            setMeth = 'set' + meth
            # Define public method for retrieving a copy of data array
            def getData(self, var=field.var):
                array = self._ag._data[var]
                if array is None:
                    return None
                return array[self._index] 
            getData = wrapGetMethod(getData)
            getData.__name__ = getMeth
            getData.__doc__ = field.getDocstr('set', False)
            setattr(cls, getMeth, getData)
            setattr(cls, '_' + getMeth, getData)
            
            # Define public method for setting values in data array
            def setData(self, value, var=field.var, none=field.none):
                array = self._ag._data[var]
                if array is None:
                    raise AttributeError('attribute of the AtomGroup is '
                                         'not set')
                array[self._index] = value
                if None:
                    self._ag.__setattr__('_' + none,  None)
            setData = wrapSetMethod(setData)
            setData.__name__ = setMeth 
            setData.__doc__ = field.getDocstr('set', False)
            setattr(cls, setMeth, setData)
            
            if field.depr:
                depr = field.depr
                getDepr = 'get' + depr
                setDepr = 'set' + depr
                
                # Define public method for retrieving a copy of data array
                def getData(self, old=getDepr, new=getMeth):
                    prody.deprecate(old, new, 4)
                    return self.__getattribute__(new)() 
                getData = wrapGetMethod(getData)
                getData.__name__ = getDepr
                getData.__doc__ = 'Deprecated, use :meth:`{0:s}`'.format(getMeth)
                setattr(cls, getDepr, getData)
                
                # Define public method for setting values in data array
                def setData(self, value, old=setDepr, new=setMeth):
                    prody.deprecate(old, new, 4)
                    self.__getattribute__(new)(value)
                setData = wrapSetMethod(setData)
                setData.__name__ = setDepr 
                setData.__doc__ = 'Deprecated, use :meth:`{0:s}`'.format(setMeth)
                setattr(cls, setDepr, setData)
                

class Atom(AtomPointer):
    
    """A class for accessing and manipulating attributes of an atom 
    in a :class:`AtomGroup` instance.
    
    """
    
    __metaclass__ = AtomMeta
    __slots__ = ['_ag', '_index', '_acsi']
    
    def __init__(self, atomgroup, index, acsi=None):
        AtomPointer.__init__(self, atomgroup, acsi)
        self._index = int(index)
        
    def __repr__(self):
        n_csets = self._ag.numCoordsets()
        if n_csets > 0:
            return ('<Atom: {0:s} from {1:s} (index {2:d}; {3:d} '
                    'coordinate sets, active set index: {4:d})>').format(
                    self.getName(), self._ag.getTitle(), self._index,  
                    n_csets, self._acsi)
        else:
            return ('<Atom: {0:s} from {1:s} (index {2:d}; {3:d} '
                    'coordinate sets)>').format(self.getName(), 
                    self._ag.getTitle(), self._index, n_csets)
                    
        sn = self.getSerial()
        if sn is None: 
            return ('<Atom: {0:s} from {1:s} (index {2:d}; {3:d} '
                    'coordinate sets, active set index: {4:d})>').format(
                    self.getName(), self._ag.getTitle(), self._index,  
                    self._ag.numCoordsets(), self._acsi)
        return ('<Atom: {0:s} from {1:s} (index {2:d}; sn {5:d}; {3:d} '
                'coordinate sets, active set index: {4:d})>').format(
                self.getName(), self._ag.getTitle(), self._index,  
                self._ag.numCoordsets(), self._acsi, sn)

    def __str__(self):
        return 'Atom {0:s} (index {1:d})'.format(self.getName(), self._index)
        sn = self.getSerial()
        if sn is None: 
            return 'Atom {0:s} (index {1:d})'.format(self.getName(), 
                                                     self._index)
        return 'Atom {0:s} (index {1:d}; sn {2:d})'.format(self.getName(), 
                                                           self._index, sn)

    def __len__(self):
        return 1
    
    def getIndex(self):
        """Return index of the atom."""
        
        return self._index
    
    def getAttribute(self, name):
        """Deprecated, use :meth:`getData`."""
        
        prody.deprecate('getAttribute', 'getData')
        return self.getData(name)
        
    def getData(self, label):
        """Return data *label*, if it exists.
        
        .. versionadded:: 0.7.1"""
        
        if self._ag.isData(label):
            return self._ag._data[label][self._index]
    
    _getData = getData
    
    def setAttribute(self, name, data):
        """Deprecated, use :meth:`setData`."""
        
        prody.deprecate('setAttribute', 'setData')
        return self.setData(name, data)
        
    def setData(self, label, data):
        """Update *data* with *label* for the atom.
        
        .. versionadded:: 0.7.1
        
        :raise AttributeError: when data *label* is not present"""
        
        if self._ag.isData(label):
            self._ag._data[label][self._index] = data 
        else:
            raise AttributeError("AtomGroup '{0:s}' has no data associated "
                      "with label '{1:s}'".format(self._ag.getTitle(), label))

    def getIndices(self):
        """Return index of the atom in an :class:`numpy.ndarray`."""
        
        return np.array([self._index])
    
    def getCoordinates(self):
        """Deprecated, use :meth:`getCoords`."""
        
        prody.deprecate('getCoordinates', 'getCoords')
        return self.getCoords()
        
    def getCoords(self):
        """Return a copy of coordinates of the atom from the active coordinate 
        set."""
        
        if self._ag._coordinates is None:
            return None
        return self._ag._coordinates[self._acsi, self._index].copy()
    
    def _getCoords(self):
        """Return a view of coordinates of the atom from the active coordinate 
        set."""
        
        if self._ag._coordinates is None:
            return None
        return self._ag._coordinates[self._acsi, self._index]
    
    def setCoordinates(self, coordinates):
        """Deprecated, use :meth:`setCoords`."""
        
        prody.deprecate('setCoordinates', 'setCoords')
        return self.setCoords(coordinates)
        
    def setCoords(self, coords):
        """Set coordinates of the atom in the active coordinate set."""
        
        self._ag._coordinates[self._acsi, self._index] = coords
        self._ag._setTimeStamp(self._acsi)
        
    def getCoordsets(self, indices=None):
        """Return a copy of coordinate set(s) at given *indices*, which may be 
        an integer or a list/array of integers."""
        
        if self._ag._coordinates is None:
            return None
        if indices is None:
            return self._ag._coordinates[:, self._index].copy()
        if isinstance(indices, (int, slice)):
            return self._ag._coordinates[indices, self._index].copy()
        if isinstance(indices, (list, np.ndarray)):
            return self._ag._coordinates[indices, self._index]
        raise IndexError('indices must be an integer, a list/array of integers, '
                         'a slice, or None')
       
    def _getCoordsets(self, indices=None): 
        """Return a view of coordinate set(s) at given *indices*."""
        
        if self._ag._coordinates is None:
            return None
        if indices is None:
            return self._ag._coordinates[:, self._index]
        if isinstance(indices, (int, slice)):
            return self._ag._coordinates[indices, self._index]
        if isinstance(indices, (list, np.ndarray)):
            return self._ag._coordinates[indices, self._index]
        raise IndexError('indices must be an integer, a list/array of integers, '
                         'a slice, or None')

    def iterCoordsets(self):
        """Iterate over coordinate sets by returning a copy of each 
        coordinate set."""
        
        for i in range(self._ag._n_csets):
            yield self._ag._coordinates[i, self._index].copy()


    def _iterCoordsets(self):
        """Iterate over coordinate sets by returning a view of each coordinate
        set."""
        
        for i in range(self._ag._n_csets):
            yield self._ag._coordinates[i, self._index]

    def getSelectionString(self):
        """Deprecated, use :meth:`getSelstr`."""
        
        prody.deprecate('getSelectionString', 'getSelstr')
        return self.getSelstr()
        
    def getSelstr(self):
        """Return selection string that will select this atom."""
        
        return 'index {0:d}'.format(self._index)


class AtomSubsetMeta(type):

    def __init__(cls, name, bases, dict):

        for field in ATOMIC_DATA_FIELDS.values():
            meth = field.meth_pl
            getMeth = 'get' + meth
            setMeth = 'set' + meth
            # Define public method for retrieving a copy of data array
            def getData(self, var=field.var):
                array = self._ag._data[var]
                if array is None:
                    return None
                return array[self._indices] 
            getData = wrapGetMethod(getData)
            getData.__name__ = getMeth
            getData.__doc__ = field.getDocstr('get')
            setattr(cls, getMeth, getData)
            setattr(cls, '_' + getMeth, getData)
            
            # Define public method for setting values in data array
            def setData(self, value, var=field.var, none=field.none):
                array = self._ag._data[var]
                if array is None:
                    raise AttributeError(var + ' data is not set')
                array[self._indices] = value
                if none:
                    self._ag.__setattr__('_'+none,  None)
            setData = wrapSetMethod(setData)
            setData.__name__ = setMeth 
            setData.__doc__ = field.getDocstr('set')  
            setattr(cls, setMeth, setData)

            # DEPRECATIONS
            if field.depr:
                depr = field.depr_pl
                getDepr = 'get' + depr
                setDepr = 'set' + depr
                # Define public method for retrieving a copy of data array
                def getData(self, old=getDepr, new=getMeth):
                    prody.deprecate(old, new, 4)
                    return self.__getattribute__(new)() 
                getData = wrapGetMethod(getData)
                getData.__name__ = getDepr
                getData.__doc__ = 'Deprecated, use :meth:`{0:s}`'.format(getMeth)
                setattr(cls, getDepr, getData)
                setattr(cls, '_' + getDepr, getData)
                
                # Define public method for setting values in data array
                def setData(self, value, old=setDepr, new=setMeth):
                    prody.deprecate(old, new, 4)
                    self.__getattribute__(new)(value)
                setData = wrapSetMethod(setData)
                setData.__name__ = setDepr 
                setData.__doc__ = 'Deprecated, use :meth:`{0:s}`'.format(setMeth)
                setattr(cls, setDepr, setData)
                        
class AtomSubset(AtomPointer):
    
    """A class for manipulating subset of atomic data in an :class:`AtomGroup`.
    
    This class stores a reference to an :class:`AtomGroup` instance, a set of 
    atom indices, and active coordinate set index for the atom group.
    
    """
    
    __metaclass__ = AtomSubsetMeta    
    __slots__ = ['_ag', '_indices', '_acsi']
    
    def __init__(self, atomgroup, indices, acsi=None, **kwargs):
        """Instantiate atom group base class. 
        
        :arg atomgroup: an atom group
        :type atomgroup: :class:`AtomGroup`
        
        :arg indices: list of indices of atoms in the subset
        :type indices: list of integers
        
        :arg acsi: active coordinate set index
        :type acsi: integer
        """
        
        AtomPointer.__init__(self, atomgroup, acsi)
        if not isinstance(indices, np.ndarray):
            indices = np.array(indices, int)
        elif not indices.dtype == int:
            indices = indices.astype(int)
        if kwargs.get('unique'):
            self._indices = indices
        else:
            self._indices = np.unique(indices)
    
    def __iter__(self):
        """Iterate over atoms."""
        
        acsi = self._acsi
        ag = self._ag 
        for index in self._indices:
            yield Atom(ag, index, acsi)
    
    def __len__(self):
        return len(self._indices)
    
    def __invert__(self):
        arange = range(self._ag.numAtoms())
        indices = list(self._indices)
        while indices:
            arange.pop(indices.pop())
        sel = Selection(self._ag, arange, "not ({0:s}) ".format(
                                                 self.getSelstr()), self._acsi)        
        return sel
    
    def __or__(self, other):
        if not isinstance(other, AtomSubset):
            raise TypeError('other must be an AtomSubset')
        if self._ag != other._ag:
            raise ValueError('both selections must be from the same AtomGroup')
        if self is other:
            return self
        acsi = self._acsi
        if acsi != other._acsi:
            LOGGER.warning('active coordinate set indices do not match, '
                           'so it will be set to zero in the union.')
            acsi = 0
        if isinstance(other, Atom):
            other_indices = np.array([other._index])
        else:
            other_indices = other._indices
        indices = np.unique(np.concatenate((self._indices, other_indices)))
        return Selection(self._ag, indices, '({0:s}) or ({1:s})'.format(
                                    self.getSelstr(), other.getSelstr()), acsi)

    def __and__(self, other):
        """
        .. versionchanged:: 0.7.1
           If intersection of selections does not contain any atoms, ``None``
           is returned."""
        
        if not isinstance(other, AtomSubset):
            raise TypeError('other must be an AtomSubset')
        if self._ag != other._ag:
            raise ValueError('both selections must be from the same AtomGroup')
        if self is other:
            return self
        acsi = self._acsi
        if acsi != other._acsi:
            LOGGER.warning('active coordinate set indices do not match, '
                           'so it will be set to zero in the union.')
            acsi = 0
        indices = set(self._indices)
        if isinstance(other, Atom):
            other_indices = set([other._index])
        else:
            other_indices = set(other._indices)
        indices = indices.intersection(other_indices)
        if indices:
            indices = np.unique(indices)
            return Selection(self._ag, indices, '({0:s}) and ({1:s})'.format(
                                    self.getSelstr(), other.getSelstr()), acsi)
               
    def getAttribute(self, name):
        """Deprecated, use :meth:`getData`."""
        
        prody.deprecate('getAttribute', 'getData')
        return self.getData(name)
        
    def getData(self, label):
        """Return a copy of the data associated with *label*, if it exists.
        
        .. versionadded:: 0.7.1"""
        
        if self._ag.isData(label):
            return self._ag._data[label][self._indices]
    
    _getData = getData
    
    def setAttribute(self, name, data):
        """Deprecated, use :meth:`setData`."""
        
        prody.deprecate('setAttribute', 'setData')
        return self.setData(name, data)
        
    def setData(self, label, data):
        """Update *data* with label *label* for the atom subset.
        
        .. versionadded:: 0.7.1
        
        :raise AttributeError: when data associated with *label* is not present
        """
        
        if self._ag.isData(label):
            self._ag._data[label][self._indices] = data 
        else:
            raise AttributeError("AtomGroup '{0:s}' has no data with label "
                            "'{1:s}'".format(self._ag.getTitle(), label))
    
    def getIndices(self):
        """Return a copy of the indices of atoms."""
        
        return self._indices.copy()
    
    def getNumOfAtoms(self):
        """Deprecated, use :meth:`numAtoms`."""
        
        prody.deprecate('getNumOfAtoms', 'numAtoms')
        return self.numAtoms()
        
    def numAtoms(self):
        """Return number of atoms."""
        
        return self._indices.__len__()

    def getCoordinates(self):
        """Deprecated, use :meth:`getCoords`."""
        
        prody.deprecate('getCoordinates', 'getCoords')
        return self.getCoords()
        
    def getCoords(self):
        """Return a copy of coordinates from the active coordinate set."""
        
        if self._ag._coordinates is None:
            return None
        # Since this is not slicing, a view is not returned
        return self._ag._coordinates[self._acsi, self._indices]
    
    _getCoords = getCoords
    
    def setCoordinates(self, coordinates):
        """Deprecated, use :meth:`setCoords`."""
        
        prody.deprecate('setCoordinates', 'setCoords')
        return self.setCoords(coordinates)
        
    def setCoords(self, coords):
        """Set coordinates in the active coordinate set."""
        
        self._ag._coordinates[self._acsi, self._indices] = coords
        self._ag._setTimeStamp(self._acsi)
        
    def getCoordsets(self, indices=None):
        """Return coordinate set(s) at given *indices*, which may be an integer 
        or a list/array of integers."""
        
        if self._ag._coordinates is None:
            return None
        if indices is None:
            return self._ag._coordinates[:, self._indices]
        if isinstance(indices, (int, slice)):
            return self._ag._coordinates[indices, self._indices]
        if isinstance(indices, (list, np.ndarray)):
            return self._ag._coordinates[indices, self._indices]
        raise IndexError('indices must be an integer, a list/array of '
                         'integers, a slice, or None')
                         
    _getCoordsets = getCoordsets

    def iterCoordsets(self):
        """Iterate over coordinate sets by returning a copy of each coordinate 
        set."""
        
        for i in range(self._ag._n_csets):
            yield self._ag._coordinates[i, self._indices]

    _iterCoordsets = iterCoordsets

class Chain(AtomSubset):
    
    """Instances are generated by :class:`HierView` class.
    
    Indexing a :class:`Chain` instance by residue number returns 
    :class:`Residue` instances.
    
    >>> from prody import *
    >>> pdb = parsePDB('1p38')
    >>> hv = pdb.getHierView()
    >>> chA = hv['A']
    >>> chA[4]
    <Residue: GLU 4 from Chain A from 1p38 (9 atoms; 1 coordinate sets, active set index: 0)>
    >>> print chA[3] # Residue 3 does not exist in chain A
    None
    
    Iterating over a chain yields residue instances:
        
    >>> for res in chA: print res
    GLU 4
    ARG 5
    PRO 6
    THR 7
    ...
    """
        
    __slots__ = AtomSubset.__slots__ + ['_seq', '_dict']
    
    def __init__(self, atomgroup, indices, acsi=None, **kwargs):
        AtomSubset.__init__(self, atomgroup, indices, acsi, **kwargs)
        self._seq = None
        self._dict = OrderedDict()
        
    def __len__(self):
        return len(self._dict)
    
    def __repr__(self):
        n_csets = self._ag.numCoordsets()
        if n_csets > 0:
            return ('<Chain: {0:s} from {1:s} ({2:d} atoms; '
                    '{3:d} coordinate sets, active set index: {4:d})>').format(
                    self.getIdentifier(), self._ag.getTitle(), 
                    self.numAtoms(), n_csets, self._acsi)
        else:
            return ('<Chain: {0:s} from {1:s} ({2:d} atoms; '
                    '{3:d} coordinate sets)>').format(self.getIdentifier(), 
                    self._ag.getTitle(), self.numAtoms(), n_csets)

    def __str__(self):
        return ('Chain {0:s}').format(self.getIdentifier())

    def __iter__(self):
        return self.iterResidues()
    
    def __getitem__(self, number):
        """Returns the residue with given number, if it exists.
        
        .. versionchanged:: 6.2
           Tuples composed of chain identifier, residue number, and residue
           insertion code is accepted."""
        
        if isinstance(number, tuple): 
            if len(number) == 2:
                return self.getResidue(number[0], number[1]) 
            else:
                return self.getResidue(number[0])
        return self.getResidue(number)
    
    def getResidue(self, number, insertcode=''):
        """Return residue with given number."""
        
        return self._dict.get((number, insertcode), None)

    def iterResidues(self):
        """Iterate residues in the chain."""
        
        #keys = self._dict.keys()
        #keys.sort()
        #for key in keys:
        #    yield self._dict[key]
        for res in self._dict.itervalues():
            yield res
    
    def getNumOfResidues(self):
        """Deprecated, use :meth:`numResidues`."""
        
        prody.deprecate('getNumOfResidues', 'numResidues')
        return self.numResidues()
        
    def numResidues(self):
        """Return number of residues."""
        
        return len(self._dict)

    def getIdentifier(self):
        """Return chain identifier."""
        
        return self._ag._data['chids'][self._indices[0]]
    
    def setIdentifier(self, chid):
        """Set chain identifier."""
        
        self.setChids(chid)
    
    def getSequence(self):
        """Return sequence, if chain is a polypeptide."""
        
        if self._seq:
            return self._seq
        CAs = self.select('name CA').select('protein')
        if len(CAs) > 0:
            self._seq = prody.compare.getSequence(CAs.getResnames())
        else:
            self._seq = ''
        return self._seq

    def getSelectionString(self):
        """Deprecated, use :meth:`getSelstr`."""
        
        prody.deprecate('getSelectionString', 'getSelstr')
        return self.getSelstr()
        
    def getSelstr(self):
        """Return selection string that selects this chain."""
        
        return 'chain {0:s}'.format(self.getIdentifier())


class Residue(AtomSubset):
    
    """Instances are generated by :class:`HierView` class.
    
    Indexing a :class:`Residue` by atom name returns :class:`Atom` instances.
    
    >>> from prody import *
    >>> pdb = parsePDB('1p38')
    >>> hv = pdb.getHierView()
    >>> chA = hv['A']
    >>> res = chA[4]
    >>> res['CA']
    <Atom: CA from 1p38 (index 1; 1 coordinate sets, active set index: 0)>
    >>> res['CB']
    <Atom: CB from 1p38 (index 4; 1 coordinate sets, active set index: 0)>
    >>> print res['H'] # X-ray structure 1p38 does not contain H atoms
    None
    
    """
     
    __slots__ = AtomSubset.__slots__ + ['_chain']
    
    def __init__(self, atomgroup, indices, chain, acsi=None, **kwargs):
        AtomSubset.__init__(self, atomgroup, indices, acsi, **kwargs)
        self._chain = chain

    def __repr__(self):
        n_csets = self._ag.numCoordsets()
        if n_csets > 0:
            return ('<Residue: {0:s} {1:d}{2:s} from Chain {3:s} from {4:s} '
                    '({5:d} atoms; {6:d} coordinate sets, active set index: '
                    '{7:d})>').format(self.getName(), self.getNumber(), 
                                      self.getIcode(), 
                                      self.getChain().getIdentifier(), 
                                      self._ag.getTitle(), len(self), 
                                      n_csets, self._acsi)
        else:        
            return ('<Residue: {0:s} {1:d}{2:s} from Chain {3:s} from {4:s} '
                    '({5:d} atoms; {6:d} coordinate sets)>').format(
                        self.getName(), self.getNumber(), 
                        self.getIcode(), 
                        self.getChain().getIdentifier(), 
                        self._ag.getTitle(), len(self), n_csets)
            
    def __str__(self):
        return '{0:s} {1:d}{2:s}'.format(self.getName(), self.getNumber(), 
                                         self.getIcode())

    def __getitem__(self, name):
        return self.getAtom(name)
    
    def getAtom(self, name):
        """Return atom with given *name*, ``None`` if not found.  Assumes that 
        atom names in a residue are unique.  If more than one atoms with the 
        given *name* exists, the one with the smaller index will be returned.
        """
        
        if isinstance(name, str):
            nz = (self.getNames() == name).nonzero()[0]
            if len(nz) > 0:
                return Atom(self._ag, self._indices[nz[0]], self._acsi)
    
    def getChain(self):
        """Return the chain that the residue belongs to."""
        
        return self._chain
    
    def getNumber(self):
        """Return residue number."""
        
        return int(self._ag._data['resnums'][self._indices[0]])
    
    def setNumber(self, number):
        """Set residue number."""
        
        self.setResnums(number)
    
    def getName(self):
        """Return residue name."""
        
        return self._ag._data['resnames'][self._indices[0]]
    
    def setName(self, name):
        """Set residue name."""
        
        self.setResnames(name)

    def getInsertionCode(self):
        """Deprecated, use :meth:`getIcode`."""
        
        prody.deprecate('getInsertionCode', 'getIcode')
        return self.getIcode()
        
    def getIcode(self):
        """Return residue insertion code."""
        
        return self._ag._data['icodes'][self._indices[0]]
        
    def setInsertionCode(self, icode):
        """Deprecated, use :meth:`setIcode`."""
        
        prody.deprecate('setInsertionCode', 'setIcode')
        return self.setIcode(icode)
        
    def setIcode(self, icode):
        """Set residue insertion code."""
        
        self.setIcodes(icode)
    
    def getChainIdentifier(self):
        """Deprecated, use :meth:`getChid`."""
        
        prody.deprecate('getChainIdentifier', 'getChid')
        return self.getChid()
        
    def getChid(self):
        """Return chain identifier."""
        
        return self._chain.getIdentifier()
    
    def getSelectionString(self):
        """Deprecated, use :meth:`getSelstr`."""
        
        prody.deprecate('getSelectionString', 'getSelstr')
        return self.getSelstr()
        
    def getSelstr(self):
        """Return selection string that will select this residue."""
        
        return 'chain {0:s} and resnum {1:d}{2:s}'.format(self.getChid(), 
                                            self.getNumber(), self.getIcode())


class Selection(AtomSubset):
    
    """A class for accessing and manipulating attributes of select of atoms 
    in an :class:`AtomGroup` instance.
    
    """
    
    __slots__ = AtomSubset.__slots__ + ['_selstr']
    
    def __init__(self, atomgroup, indices, selstr, acsi=None, **kwargs):
        AtomSubset.__init__(self, atomgroup, indices, acsi, **kwargs)
        self._selstr = str(selstr)
        
    def __repr__(self):
        n_csets = self._ag.numCoordsets()
        selstr = self._selstr
        if len(selstr) > 33:
            selstr = selstr[:15] + '...' + selstr[-15:]  
        if n_csets > 0:
            return ('<Selection: "{0:s}" from {1:s} ({2:d} atoms; '
                    '{3:d} coordinate sets, active set index: {4:d})>').format(
                    selstr, self._ag.getTitle(), len(self), n_csets, 
                    self._acsi)
        else:
            return ('<Selection: "{0:s}" from {1:s} ({2:d} atoms; '
                    '{3:d} coordinate sets)>').format(
                    selstr, self._ag.getTitle(), len(self), n_csets)

    def __str__(self):
        selstr = self._selstr
        if len(selstr) > 33:
            selstr = selstr[:15] + '...' + selstr[-15:]  
        return 'Selection "{0:s}" from {1:s}'.format(selstr, 
                                                     self._ag.getTitle())
    
    def getSelectionString(self):
        """Deprecated, use :meth:`getSelstr`."""
        
        prody.deprecate('getSelectionString', 'getSelstr')
        return self.getSelstr()
        
    def getSelstr(self):
        """Return selection string that selects this atom subset."""
        
        return self._selstr

    def getHierView(self):
        """Return a hierarchical view of the atom selection."""
        
        return HierView(self)


class AtomMapMeta(type):
    
    def __init__(cls, name, bases, dict):
        for field in ATOMIC_DATA_FIELDS.values():
            meth = field.meth_pl
            getMeth = 'get' + meth
            def getData(self, var=field.var, dtype=field.dtype):
                array = self._ag._data[var]
                if array is None:
                    return None
                data = self._ag._data[var][self._indices]
                result = np.zeros((self._len,) + data.shape[1:], dtype)
                result[self._mapping] = data
                return result 
            getData = wrapGetMethod(getData)
            getData.__name__ = getMeth
            if field.dtype in (int, float):
                zero = '0'
            elif field.dtype == bool:
                zero = 'True'
            else:
                zero = '""'
            getData.__doc__ = field.getDocstr('get', selex=False) + \
                   'Entries for unmapped atoms will be ``{0:s}``.'.format(zero) 
            setattr(cls, getMeth, getData)
            setattr(cls, '_' + getMeth, getData)
        
            if field.depr:
                depr = field.depr_pl
                getDepr = 'get' + depr
                def getData(self, old=getDepr, new=getMeth):
                    prody.deprecate(old, new, 4)
                    return self.__getattribute__(new)()
                getData = wrapGetMethod(getData)
                getData.__name__ = getDepr
                getData.__doc__ = 'Deprecated, use :meth:`{0:s}`'.format(getMeth) 
                setattr(cls, getDepr, getData)
             


class AtomMap(AtomPointer):
    
    """A class for mapping atomic data.
    
    This class stores a reference to an :class:`AtomGroup` instance, a set of 
    atom indices, active coordinate set index, mapping for indices, and
    indices of unmapped atoms.
    
    """
    
    __metaclass__ = AtomMapMeta
    __slots__ = ['_ag', '_indices', '_acsi', '_title', '_mapping', '_unmapped', 
                 '_len']
    
    def __init__(self, atomgroup, indices, mapping, unmapped, title='Unnamed', 
                 acsi=None):
        """Instantiate with an AtomMap with following arguments:        
        
        :arg atomgroup: the atomgroup instance from which atoms are mapped
        :arg indices: indices of mapped atoms
        :arg mapping: mapping of the atoms as a list of indices
        :arg unmapped: list of indices for unmapped atoms
        :arg title: title of the AtomMap instance
        :arg acsi: active coordinate set index, if ``None`` defaults to that 
            of *atomgrup*
        
        Length of *mapping* must be equal to length of *indices*.  Number of 
        atoms (including unmapped dummy atoms) are determined from the sum of 
        lengths of *mapping* and *unmapped* arrays."""
        
        AtomPointer.__init__(self, atomgroup, acsi)
        
        if not isinstance(indices, np.ndarray):
            self._indices = np.array(indices, int)
        elif not indices.dtype == int:
            self._indices = indices.astype(int)
        else:
            self._indices = indices

        if not isinstance(mapping, np.ndarray):
            self._mapping = np.array(mapping, int)
        elif not mapping.dtype == int:
            self._mapping = mapping.astype(int)
        else:
            self._mapping = mapping

        if not isinstance(unmapped, np.ndarray):
            self._unmapped = np.array(unmapped, int)
        elif not unmapped.dtype == int:
            self._unmapped = unmapped.astype(int)
        else:
            self._unmapped = unmapped
        
        self._title = str(title)
        self._len = len(self._unmapped) + len(self._mapping)
        
    def __repr__(self):
        n_csets = self._ag.numCoordsets()
        if n_csets > 0:
            return ('<AtomMap: {0:s} (from {1:s}; {2:d} atoms; '
                    '{3:d} mapped; {4:d} unmapped; {5:d} coordinate sets, '
                    'active set index: {6:d})>').format(self._title,
                    self._ag.getTitle(), self._len, len(self._mapping), 
                    len(self._unmapped), n_csets, self._acsi)
        else:
            return (('<AtomMap: {0:s} (from {1:s}; {2:d} atoms; '
                    '{3:d} mapped; {4:d} unmapped; {5:d} coordinate sets)>')
                    .format(self._title, self._ag.getTitle(), self._len, 
                    len(self._mapping), len(self._unmapped), n_csets))
            
    def __str__(self):
        return 'AtomMap {0:s}'.format(self._title)
    
    def __iter__(self):
        indices = np.zeros(self._len, int)
        indices[self._unmapped] = -1
        indices[self._mapping] = self._indices
        ag = self._ag
        acsi = self._acsi
        for index in indices:
            if index > -1:
                yield Atom(ag, index, acsi)
            else:
                yield None
    
    def __len__(self):
        return self._len
    
    def getAttribute(self, name):
        """Deprecated, use :meth:`getData`."""
        
        prody.deprecate('getAttribute', 'getData')
        return self.getData(name)
        
    def getData(self, label):
        """Return a copy of data associated with *label*, if it exists.
        
        .. versionadded:: 0.7.1"""
        
        if self._ag.isData(label):
            data = self._ag._data[label][self._indices]
            result = np.zeros((self._len,) + data.shape[1:], data.dtype)
            result[self._mapping] = data
            return result

    _getData = getData

    def getName(self):
        """Deprecated, use :meth:`getTitle`."""

        prody.deprecate('getName', 'getTitle')
        return self.getTitle()
        
    def getTitle(self):
        """Return title of the atom map instance."""
        
        return self._title
    
    def setName(self, name):
        """Deprecated, use :meth:`setTitle`."""

        prody.deprecate('setName', 'setTitle')
        return self.setTitle(name)
        
    def setTitle(self, title):
        """Set title of the atom map instance."""
        
        self._title = str(title)

    def getNumOfAtoms(self):
        """Deprecated, use :meth:`numAtoms`."""

        prody.deprecate('getNumOfAtoms', 'numAtoms')
        return self.numAtoms()
        
    def numAtoms(self):
        """Return number of mapped atoms."""
        
        return self._len

    def getNumOfUnmapped(self):
        """Deprecated, use :meth:`numUnmapped`."""

        prody.deprecate('getNumOfUnmapped', 'numUnmapped')
        return self.numUnmapped()
        
    def numUnmapped(self):
        """Return number of unmapped atoms."""
        
        return len(self._unmapped)

    def getNumOfMapped(self):
        """Deprecated, use :meth:`numMapped`."""

        prody.deprecate('getNumOfMapped', 'numMapped')
        return self.numMapped()
        
    def numMapped(self):
        """Return number of mapped atoms."""
        
        return len(self._mapping)

    def getIndices(self):
        """Return indices of mapped atoms."""
        
        return self._indices.copy()

    def getMapping(self):
        """Return mapping of indices."""
        
        return self._mapping.copy()

    def iterCoordsets(self):
        """Iterate over coordinate sets by returning a copy of each coordinate 
        set."""
        
        for i in range(self._ag._n_csets):
            coordinates = np.zeros((self._len, 3), float)
            coordinates[self._mapping] = self._ag._coordinates[i, 
                                                               self._indices] 
            yield coordinates
    
    _iterCoordsets = iterCoordsets

    def getCoordinates(self):
        """Deprecated, use :meth:`getCoords`."""
        
        prody.deprecate('getCoordinates', 'getCoords')
        return self.getCoords()
        
    def getCoords(self):
        """Return coordinates from the active coordinate set."""
        
        if self._ag._coordinates is None:
            return None
        coordinates = np.zeros((self._len, 3), float)
        coordinates[self._mapping] = self._ag._coordinates[self._acsi, 
                                                           self._indices] 
        return coordinates
    
    _getCoords = getCoords
    
    def setCoordinates(self, coordinates):
        """Deprecated, use :meth:`setCoords`."""
        
        prody.deprecate('setCoordinates', 'setCoords')
        return self.setCoords(coordinates)
        
    def setCoords(self, coords):
        """Set coordinates in the active coordinate set.  Length of the 
        *coordinates* array must match the number of mapped atoms."""
        
        self._ag._coordinates[self._acsi, self._indices] = coords
    

    def getCoordsets(self, indices=None):
        """Return coordinate set(s) at given *indices*, which may be an integer 
        or a list/array of integers."""
        
        if self._ag._coordinates is None:
            return None
        if indices is None:
            indices = np.arange(self._ag._n_csets)
        elif isinstance(indices, (int, long)):
            indices = np.array([indices])
        elif isinstance(indices, slice):
            indices = np.arange(indices.indices(self._ag._n_csets))
        try:
            coordsets = np.zeros((len(indices), self._len, 3))
            coordsets[:, self._mapping] = self._ag._coordinates[indices][:, 
                                                                self._indices]  
            return coordsets
        except IndexError:
            raise IndexError('indices may be an integer or a list/array '
                             'of integers')

    _getCoordsets = getCoordsets

    def getUnmappedFlags(self):
        """Return an array with 1s for unmapped atoms."""
        
        flags = np.zeros(self._len)
        if len(self._unmapped):
            flags[self._unmapped] = 1
        return flags
    
    def getMappedFlags(self):
        """Return an array with 1s for mapped atoms."""
        
        flags = np.ones(self._len)
        if len(self._unmapped):
            flags[self._unmapped] = 0
        return flags

class HierView(object):
    
    """Hierarchical views can be generated for :class:`AtomGroup` and 
    :class:`Selection` instances.  Indexing a :class:`HierView` instance 
    returns a :class:`Chain` instance.
    
    >>> from prody import *
    >>> pdb = parsePDB('1p38')
    >>> hv = pdb.getHierView()
    >>> chA = hv['A']
    >>> chA
    <Chain: A from 1p38 (2962 atoms; 1 coordinate sets, active set index: 0)>
    >>> print hv['B'] # Chain B does not exist in 1p38
    None
    
    """
    
    __slots__ = ['_atoms', '_chains']

    def __init__(self, atoms, **kwargs):
        if not isinstance(atoms, Atomic):
            raise TypeError('atoms must be an atomic instance')
        self._atoms = atoms
        self.update(**kwargs)

    def getAtoms(self):
        """Return atoms for which the hierarchical view is built.
        
        .. versionadded:: 0.6.2"""
        
        return self._atoms
    
    
    def update(self, **kwargs):
        """Rebuild hierarchical view of atoms.  This method is called at 
        instantiation, but can be used to rebuild the hierarchical view 
        when attributes of atoms change."""
        
        array = np.array
        acsi = self._atoms.getACSIndex()
        atoms = self._atoms
        if isinstance(atoms, AtomGroup):
            atomgroup = atoms
            _indices = np.arange(atomgroup._n_atoms)
            chids = atomgroup._getChids() 
            if chids is None:
                chids = np.zeros(atomgroup._n_atoms, 
                                 dtype=ATOMIC_DATA_FIELDS['chain'].dtype)
                atomgroup.setChids(chids)
        else:
            atomgroup = atoms._ag
            _indices = atoms._indices
            chids = atomgroup._getChids() 
            if chids is None:
                chids = np.zeros(atomgroup._n_atoms, 
                                 dtype=ATOMIC_DATA_FIELDS['chain'].dtype)
                atomgroup.setChids(chids)
            chids = chids[_indices]

        self._chains = _chains = OrderedDict()
        prev = None          
        for i, chid in enumerate(chids):
            if chid == prev or chid in _chains:
                continue
            prev = chid
            _chains[chid] = Chain(atomgroup, _indices[i:][chids[i:] == chid], 
                                  acsi, unique=True)
                                  
        if kwargs.get('chain', False):
            return
        _resnums = atomgroup._getResnums()
        if _resnums is None:
            _resnums = np.zeros(atomgroup._n_atoms, 
                                dtype=ATOMIC_DATA_FIELDS['resnum'].dtype)
            atomgroup.setResnums(_resnums)
        
        _icodes = atomgroup._getIcodes()
        skip_icodes = False
        if _icodes is None:
            skip_icodes = True
            _icodes = np.zeros(atomgroup._n_atoms, 
                              dtype=ATOMIC_DATA_FIELDS['icode'].dtype)
            atomgroup.setIcodes(_icodes)
        elif np.all(_icodes == ''):
            skip_icodes = True

        for chain in self._chains.itervalues():
            _dict = chain._dict
            _indices = chain._indices
            idx = _indices[0]
            prevrn = _resnums[idx]
            start = 0
            if skip_icodes:
                ic = ''
                for i, idx in enumerate(_indices): 
                    rn = _resnums[idx]
                    if rn != prevrn:
                        res = (prevrn, ic)
                        if res in _dict:                                
                            _dict[res] = Residue(atomgroup, 
                                                 np.concatenate((
                                                    _dict[res]._indices, 
                                                    _indices[start:i])), 
                                                 chain, acsi, unique=True)
                        else:
                            _dict[res] = Residue(atomgroup, _indices[start:i], 
                                                 chain, acsi, unique=True)
                        start = i
                        prevrn = rn
                # final residue
                res = (rn, ic)
                if res in _dict:                                
                    _dict[res] = Residue(atomgroup, 
                                         np.concatenate((_dict[res]._indices, 
                                                         _indices[start:i+1])), 
                                         chain, acsi, unique=True)
                else:
                    _dict[res] = Residue(atomgroup, _indices[start:i+1],
                                         chain, acsi, unique=True)
            else:
                previc = _icodes[idx]
                for i, idx in enumerate(_indices): 
                    rn = _resnums[idx]
                    ic = _icodes[idx]
                    if rn != prevrn or ic != previc:
                        res = (prevrn, previc)
                        if res in _dict:
                            _dict[res] = Residue(atomgroup, 
                                                 np.concatenate((
                                                    _dict[res]._indices, 
                                                    _indices[start:i])), 
                                                 chain, acsi, unique=True)
                        else:
                            _dict[res] = Residue(atomgroup, 
                                                 _indices[start:i], 
                                                 chain, acsi, unique=True)
                        start = i
                        prevrn = rn
                        previc = ic
                # final residue
                res = (rn, ic)
                if res in _dict:
                    _dict[res] = Residue(atomgroup, 
                                         np.concatenate((_dict[res]._indices,
                                                         _indices[start:i+1])), 
                                         chain, acsi, unique=True)
                else:
                    _dict[res] = Residue(atomgroup, _indices[start:i+1],
                                         chain, acsi, unique=True)
        
    def __repr__(self):
        return '<HierView: {0:s}>'.format(str(self._atoms))
    
    def __str__(self):
        return 'HierView of {0:s}'.format(str(self._atoms))
    
    def __iter__(self):
        """Iterate over chains."""
        
        return self.iterChains()
    
    def __len__(self):
        return len(self._chains)
    
    def __getitem__(self, chid):
        """
        .. versionchanged:: 6.2
           Tuples composed of chain identifier, residue number, and residue
           insertion code is accepted."""
        
        if isinstance(chid, str):
            return self._chains.get(chid, None)
        elif isinstance(chid, tuple):
            ch = self._chains.get(chid[0], None)
            if ch is not None:
                return ch[chid[1:]]

    def iterResidues(self):
        """Iterate over residues."""
        
        #chids = self._chains.keys()
        #chids.sort()
        #for chid in chids:
        #    chain = self._chains[chid]
        #    for res in chain.iterResidues():
        #        yield res
        for chain in self._chains.itervalues():
            for residue in chain.iterResidues():
                yield residue
                
    def getResidue(self, chid, resnum, icode=''):
        """Return residue with number *resnum* and insertion code *icode* from 
        the chain with identifier *chid*, if it exists."""
        
        ch = self._chains.get(chid, None)
        if ch is not None:
            return ch.getResidue(resnum, icode)
        return None

    def getNumOfResidues(self):
        """Deprecated, use :meth:`numResidues`."""
        
        prody.deprecate('getNumOfResidues', 'numResidues')
        return self.numResidues()
        
    def numResidues(self):
        """Returns number of residues."""
        
        return sum([ch.numResidues() for ch in self._chains.itervalues()])    

    def iterChains(self):
        """Iterate over chains."""
        
        #chids = self._chains.keys()
        #chids.sort()
        #for chid in chids:
        #    yield self._chains[chid]
        for chain in self._chains.itervalues():
            yield chain
    
    def getChain(self, chid):
        """Return chain with identifier *chid*, if it exists."""
        
        return self._chains.get(chid, None)

    def getNumOfChains(self):
        """Deprecated, use :meth:`numChains`."""
        
        prody.deprecate('getNumOfChains', 'numChains')
        return self.numChains()
    
    def numChains(self):
        """Return number of chains."""
        
        return len(self._chains)


def saveAtoms(atoms, filename=None, **kwargs):
    """Save *atoms* in ProDy internal format.  All classes derived from 
    :class:`Atomic` are accepted as *atoms* argument.
    
    .. versionadded:: 0.7.1
    
    This function saves user set atomic attributes as well.  Note that name of 
    the :class:`AtomGroup` instance is used as the filename when *atoms* is not
    an :class:`AtomGroup`.  This is because names for selections and atom maps
    may be too long and may contain special characters.  To avoid overwriting 
    an existing file with the same name, specify a *filename*."""
    
    if not isinstance(atoms, Atomic):
        raise TypeError('atoms must be Atomic instance, not {0:s}'
                        .format(type(atoms)))
    if isinstance(atoms, AtomGroup):
        ag = atoms
        title = ag.getTitle()
    else:
        ag = atoms.getAtomGroup()
        title = str(atoms)
    
    if filename is None:
        filename = ag.getTitle().replace(' ', '_')
    filename += '.ag.npz'
    attr_dict = {'title': title}
    attr_dict['n_atoms'] = atoms.numAtoms()
    attr_dict['n_csets'] = atoms.numCoordsets()
    attr_dict['cslabels'] = atoms.getCSLabels()
    coords = atoms._getCoordsets()
    if coords is not None:
        attr_dict['coordinates'] = coords
    for key, data in ag._data.iteritems():
        if data is not None:
            attr_dict[key] = data 
    ostream = openFile(filename, 'wb', **kwargs)
    np.savez(ostream, **attr_dict)
    ostream.close()
    return filename

SKIP = set(['_name', '_title', 'title', 'n_atoms', 'n_csets', 
            'coordinates', '_coordinates', 'cslabels'])

def loadAtoms(filename):
    """Return :class:`AtomGroup` instance from *filename*.  This function makes
    use of :func:`numpy.load` function.  See also :func:`saveAtoms`.
    
    .. versionadded:: 0.7.1"""
    
    LOGGER.timeit()
    attr_dict = np.load(filename)
    files = set(attr_dict.files)
    # REMOVE support for _coordinates IN v1.0
    if not '_coordinates' in files and not 'n_atoms' in files:
        raise ValueError("'{0:s}' is not a valid atomic data file"
                         .format(filename))
    if '_coordinates' in files:
        ag = AtomGroup(str(attr_dict['_name']))
        for attr in attr_dict.files:
            if attr == '_name':
                continue
            elif attr == '_coordinates':
                data = attr_dict[attr]
                if data.ndim > 0:
                    ag.setCoords(data)
            elif attr in ATOMIC_ATTRIBUTES: 
                field = ATOMIC_ATTRIBUTES[attr]
                data = attr_dict[attr]
                if data.ndim > 0:
                   ag.__getattribute__('set' + field.meth_pl)(data)
                else:
                    ag.__getattribute__('set' + field.meth_pl)([data])
            else:            
                data = attr_dict[attr]
                if data.ndim > 0:
                    ag.setData(attr, data)
                else:
                    ag.setData(attr, [data])
    else:        
        ag = AtomGroup(str(attr_dict['title']))
        if 'coordinates' in files:
            ag._coordinates = attr_dict['coordinates']
        ag._n_atoms = int(attr_dict['n_atoms'])
        ag._n_csets = int(attr_dict['n_csets'])
        for key, data in attr_dict.iteritems():
            if key in SKIP:
                continue
            if key in ATOMIC_ATTRIBUTES:
                ag._data[key] = data
            else:
                ag.setData(key, data)
        if ag.numCoordsets() > 0:
            ag._acsi = 0
        if 'cslabels' in files:
            ag.setCSLabels(list(attr_dict['cslabels']))
    LOGGER.timing('Atom group was loaded in %.2fs.')
    return ag

if __name__ == '__main__':
    from prody import *
    p = parsePDB('1aar')
    saveAtoms(p)
