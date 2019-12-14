"""Provides a class to allow for lazy transposing and slicing operations on h5py datasets
Example Usage:
import h5py
from lazy_ops import DatasetView


dsetview = DatasetView(dataset) # dataset is an instantiated h5py dataset
view1 = dsetview.lazy_slice[1:10:2,:,0:50:5].lazy_transpose([2,0,1]).lazy_slice[25:55,1,1:4:1,:]
A = view1[:]          # Brackets on DataSetView call the h5py slicing method, that returns dataset data
B = view1.dsetread()  # same as view1[:]

"""

import h5py
import numpy as np
import sys

class DatasetView(h5py.Dataset):

    def __init__(self, dataset: h5py.Dataset = None, slice_index=np.index_exp[:], axis_order=None):
        """
        Args:
          dataset:    the underlying dataset
          slice_index:  the aggregate slice after multiple lazy slicing
          axis_order: the aggregate axis_order after multiple transpositions
        Returns:
          lazy object of the view
        """

        h5py.Dataset.__init__(self, dataset.id)
        if axis_order is None:
            self._axis_order = list(range(len(dataset.shape)))
        else:
            self._axis_order = axis_order
        self._lazy_slice_call = False
        self._dataset = dataset
        self._lazy_shape, self._key = self._slice_shape(slice_index)

    @property
    def lazy_slice(self):
        ''' Indicator for lazy_slice calls '''
        self._lazy_slice_call = True
        return self

    @property
    def dataset(self):
        return self._dataset

    @property
    def shape(self):
        return self._lazy_shape

    def __len__(self):
        return self.len()

    def len(self):
        return self._lazy_shape[0]

    @property
    def key(self):
        """ The self.key slice is passed to the lazy instance and is not altered by the instance's init call """
        return self._key

    @property
    def axis_order(self):
        return self._axis_order

    def _slice_tuple(self, key):
        """  Allows single slice function calls
        Args:
          key: The slice object
        Returns:
          The slice object tuple
        """
        if isinstance(key, slice):
            key = key,
        else:
            key = *key,

        return key

    def _slice_shape(self, slice_):
        """  For an slice returned by _slice_composition function, finds the shape
        Args:
          slice_: The slice object
        Returns:
          slice_shape: Shape of the slice object
          slice_key: An equivalent slice tuple with positive starts and stops
        """
        slice_ = self._slice_tuple(slice_)
        # converting the slice to regular slices that only contain integers
        slice_regindices = [slice(*slice_[i].indices(self.dataset.shape[self.axis_order[i]])) for i in range(len(slice_))]
        slice_shape = ()
        for i in range(len(slice_)):
            slice_start, slice_stop, slice_step = slice_regindices[i].start, slice_regindices[i].stop, slice_regindices[i].step
            if slice_step < 1:
                raise ValueError("Slice step parameter must be positive")
            if slice_stop < slice_start:
                slice_start = slice_stop
                slice_regindices[i] = slice(slice_start, slice_stop, slice_step)
            slice_shape += (1 + (slice_stop - slice_start -1 )//slice_step if slice_stop != slice_start else 0,)
        slice_shape += self.dataset.shape[len(slice_)::]
        slice_regindices = tuple(slice_regindices)
        return slice_shape, slice_regindices

    def __getitem__(self, new_slice):
        """  supports python's colon slicing syntax 
        Args:
          new_slice:  the new slice to compose with the lazy instance's self.key slice
        Returns:
          lazy object of the view
        """
        key_reinit = self._slice_composition(new_slice)
        if self._lazy_slice_call:
            self._lazy_slice_call = False
            return DatasetView(self.dataset, key_reinit, self.axis_order)

        return DatasetView(self.dataset, key_reinit, self.axis_order).dsetread()

    def __getitem__(self, new_slice):
        """  supports python's colon slicing syntax 
        Args:
          new_slice:  the new slice to compose with the lazy instance's self.key slice
        Returns:
          lazy object of the view
        """
        key_reinit = self._slice_composition(new_slice)
        if self._lazy_slice_call:
            self._lazy_slice_call = False
            return DatasetView(self.dataset, key_reinit, self.axis_order)

        return DatasetView(self.dataset, key_reinit, self.axis_order).dsetread()


    def __call__(self, new_slice):
        """  allows lazy_slice function calls with slice objects as input"""
        return self.__getitem__(new_slice)

    def dsetread(self):
        """ Returns the data
        Returns:
          numpy array
        """
        # Note: Directly calling regionref with slices with a zero dimension does not
        # retain shape information of the other dimensions
        reversed_axis_order = sorted(range(len(self.axis_order)), key=lambda i: self.axis_order[i])
        reversed_slice_key = tuple(self.key[i] for i in reversed_axis_order if i < len(self.key))
        return self.dataset[reversed_slice_key].transpose(self.axis_order)

    def _slice_composition(self, new_slice):
        """  composes a new_slice with the self.key slice
        Args:
          new_slice: The new slice
        Returns:
          merged slice object
        """
        new_slice = self._slice_tuple(new_slice)
        new_slice = self._ellipsis_slices(new_slice)
        slice_result = ()
        # Iterating over the new slicing tuple to change the merged dataset slice.
        for i in range(len(new_slice)):
            if i < len(self.key):
                # converting new_slice slice to regular slices,
                # newkey_start, newkey_stop, newkey_step only contains positive or zero integers
                newkey_start, newkey_stop, newkey_step = new_slice[i].indices(self._lazy_shape[i])
                if newkey_step < 1:
                    # regionref requires step>=1 for dataset data calls
                    raise ValueError("Slice step parameter must be positive")
                if newkey_stop < newkey_start:
                    newkey_start = newkey_stop

                slice_result += (slice(min(self.key[i].start + self.key[i].step * newkey_start, self.key[i].stop),
                                 min(self.key[i].start + self.key[i].step * newkey_stop, self.key[i].stop),
                                 newkey_step * self.key[i].step),)
            else:
                slice_result += (slice(*new_slice[i].indices(self.dataset.shape[self.axis_order[i]])),)
        for i in range(len(new_slice), len(self.key)):
            slice_result += (slice(*self.key[i].indices(self.dataset.shape[self.axis_order[i]])),)

        return slice_result

    @property
    def T(self):
        """ Same as lazy_transpose() """
        return self.lazy_transpose()

    def lazy_transpose(self, axis_order=None):
        """ Array lazy transposition, no axis_order reverses the order of dimensions
        Args:
          axis_order: permutation order for transpose
        Returns:
          lazy object of the view
        """

        if axis_order is None:
            axis_order = list(reversed(range(len(self.axis_order))))

        axis_order_reinit = [self.axis_order[i] if i < len(self.axis_order) else i for i in axis_order]
        key_reinit = [self.key[i] if i < len(self.key) else np.s_[:] for i in axis_order]
        key_reinit.extend([self.key[i] for i in self.axis_order if i not in axis_order_reinit])
        axis_order_reinit.extend([i for i in self.axis_order if i not in axis_order_reinit])

        return DatasetView(self.dataset, key_reinit, axis_order_reinit)

    def read_direct(self, dest, source_sel=None, dest_sel=None):
        """ Using dataset.read_direct, reads data into an existing array
        Args:
          dest: C-contiguous as required by Dataset.read_direct
          source_sel: new selection slice
          dest_sel: output selection slice
        Returns:
          numpy array
        """
        if source_sel is None:
            new_key = self.key
        else:
            key_reinit = self._slice_composition(source_sel)
            _, new_key = self._slice_shape(key_reinit)
        reversed_axis_order = sorted(range(len(self.axis_order)), key=lambda i: self.axis_order[i])
        reversed_slice_key = tuple(new_key[i] for i in reversed_axis_order if i < len(new_key))
        #convert reversed_slice_key to numpy.s_[<args>] format, expected by dataset.read_direct
        if len(reversed_slice_key) == 1:
            reversed_slice_key = reversed_slice_key[0]

        reversed_dest_shape = tuple(dest.shape[i] for i in reversed_axis_order if i < len(dest.shape))
        reversed_dest = np.empty(shape=reversed_dest_shape, dtype=dest.dtype)

        if dest_sel is None:
            reversed_dest_sel = dest_sel
        else:
            reversed_dest_sel = tuple(dest_sel[i] for i in reversed_axis_order if i < len(dest_sel))
            #convert reversed_dest_sel to numpy.s_[<args>] format, expected by dataset.read_direct
            if len(reversed_slice_key) == 1:
                reversed_slice_key = reversed_slice_key[0]

        self.dataset.read_direct(reversed_dest, source_sel=reversed_slice_key, dest_sel=reversed_dest_sel)
        np.copyto(dest, reversed_dest.transpose(self.axis_order))

    def _ellipsis_slices(self, new_slice):
        """ Change Ellipsis dimensions to slices
        Args:
          new_slice: The new slice
        Returns:
          equivalent slices with Ellipsis expanded
        """
        ellipsis_count = new_slice.count(Ellipsis)
        if ellipsis_count == 1:
            ellipsis_index = new_slice.index(Ellipsis)
            if ellipsis_index == len(new_slice)-1:
                new_slice = new_slice[:-1]
            else:
                num_ellipsis_dims = len(self.dataset.shape) - (len(new_slice) - 1)
                new_slice = new_slice[:ellipsis_index] + np.index_exp[:]*num_ellipsis_dims + new_slice[ellipsis_index+1:]
        elif ellipsis_count > 0:
            raise IndexError("Only a single Ellipsis is allowed")
        return new_slice
