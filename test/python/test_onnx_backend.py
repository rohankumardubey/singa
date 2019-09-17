# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# =============================================================================

import unittest
from builtins import str

from singa import tensor
from singa import singa_wrap as singa
from singa import autograd
from singa import sonnx
from singa import opt

import onnx
from onnx import (defs, checker, helper, numpy_helper, mapping,
                  ModelProto, GraphProto, NodeProto, AttributeProto, TensorProto, OperatorSetIdProto)
from onnx.helper import make_tensor, make_tensor_value_info, make_node, make_graph

from cuda_helper import gpu_dev, cpu_dev

import numpy as np
import itertools

autograd.training = True

_default_opset_version = 10

def expect(node, inputs, outputs, name, opset_version=_default_opset_version):
    onnx_node = sonnx.OnnxNode(node)
    input_tensors = {}
    # prepare input tensors
    for key, val in zip(onnx_node.inputs, inputs):
        x = tensor.from_numpy(val)
        x.to_device(gpu_dev)
        input_tensors[key] = x
    outputs_dict = sonnx.run_node(onnx_node, input_tensors, opset_version)
    for out1, out2 in zip(outputs, outputs_dict.values()):
        np.testing.assert_array_almost_equal(out1, tensor.to_numpy(out2), decimal=5)

class TestPythonOnnxBackend(unittest.TestCase):
    """
    This class aims to test the backend functionality of sonnx,
    The most of the code is borrowed from onnx.
    """

    def test_conv2d(self):
        x = np.array([[[[0., 1., 2., 3., 4.],  # (1, 1, 5, 5) input tensor
                        [5., 6., 7., 8., 9.],
                        [10., 11., 12., 13., 14.],
                        [15., 16., 17., 18., 19.],
                        [20., 21., 22., 23., 24.]]]]).astype(np.float32)

        W = np.array([[[[1., 1., 1.],  # (1, 1, 3, 3) tensor for convolution weights
                        [1., 1., 1.],
                        [1., 1., 1.]]]]).astype(np.float32)

        # Convolution with padding
        node_with_padding = onnx.helper.make_node(
            'Conv',
            inputs=['x', 'W'],
            outputs=['y'],
            kernel_shape=[3, 3],
            # Default values for other attributes: strides=[1, 1], dilations=[1, 1], groups=1
            pads=[1, 1, 1, 1],
        )

        y_with_padding = np.array([[[[12., 21., 27., 33., 24.],  # (1, 1, 5, 5) output tensor
                                     [33., 54., 63., 72., 51.],
                                     [63., 99., 108., 117., 81.],
                                     [93., 144., 153., 162., 111.],
                                     [72., 111., 117., 123., 84.]]]]).astype(np.float32)

        expect(node_with_padding, inputs=[x, W], outputs=[y_with_padding],
               name='test_basic_conv_with_padding')

        # Convolution without padding
        node_without_padding = onnx.helper.make_node(
            'Conv',
            inputs=['x', 'W'],
            outputs=['y'],
            kernel_shape=[3, 3],
            # Default values for other attributes: strides=[1, 1], dilations=[1, 1], groups=1
            pads=[0, 0, 0, 0],
        )
        y_without_padding = np.array([[[[54., 63., 72.],  # (1, 1, 3, 3) output tensor
                                        [99., 108., 117.],
                                        [144., 153., 162.]]]]).astype(np.float32)
        expect(node_without_padding, inputs=[x, W], outputs=[y_without_padding],
               name='test_basic_conv_without_padding')

    def test_conv2d_with_strides(self):  # type: () -> None

        x = np.array([[[[0., 1., 2., 3., 4.],  # (1, 1, 7, 5) input tensor
                        [5., 6., 7., 8., 9.],
                        [10., 11., 12., 13., 14.],
                        [15., 16., 17., 18., 19.],
                        [20., 21., 22., 23., 24.],
                        [25., 26., 27., 28., 29.],
                        [30., 31., 32., 33., 34.]]]]).astype(np.float32)
        W = np.array([[[[1., 1., 1.],  # (1, 1, 3, 3) tensor for convolution weights
                        [1., 1., 1.],
                        [1., 1., 1.]]]]).astype(np.float32)

        # Convolution with strides=2 and padding
        node_with_padding = onnx.helper.make_node(
            'Conv',
            inputs=['x', 'W'],
            outputs=['y'],
            kernel_shape=[3, 3],
            pads=[1, 1, 1, 1],
            strides=[2, 2],  # Default values for other attributes: dilations=[1, 1], groups=1
        )
        y_with_padding = np.array([[[[12., 27., 24.],  # (1, 1, 4, 3) output tensor
                                     [63., 108., 81.],
                                     [123., 198., 141.],
                                     [112., 177., 124.]]]]).astype(np.float32)
        expect(node_with_padding, inputs=[x, W], outputs=[y_with_padding],
               name='test_conv_with_strides_padding')

        # Convolution with strides=2 and no padding
        node_without_padding = onnx.helper.make_node(
            'Conv',
            inputs=['x', 'W'],
            outputs=['y'],
            kernel_shape=[3, 3],
            pads=[0, 0, 0, 0],
            strides=[2, 2],  # Default values for other attributes: dilations=[1, 1], groups=1
        )
        y_without_padding = np.array([[[[54., 72.],  # (1, 1, 3, 2) output tensor
                                        [144., 162.],
                                        [234., 252.]]]]).astype(np.float32)
        expect(node_without_padding, inputs=[x, W], outputs=[y_without_padding],
               name='test_conv_with_strides_no_padding')

        # Convolution with strides=2 and padding only along one dimension (the H dimension in NxCxHxW tensor)
        node_with_asymmetric_padding = onnx.helper.make_node(
            'Conv',
            inputs=['x', 'W'],
            outputs=['y'],
            kernel_shape=[3, 3],
            pads=[1, 0, 1, 0],
            strides=[2, 2],  # Default values for other attributes: dilations=[1, 1], groups=1
        )
        y_with_asymmetric_padding = np.array([[[[21., 33.],  # (1, 1, 4, 2) output tensor
                                                [99., 117.],
                                                [189., 207.],
                                                [171., 183.]]]]).astype(np.float32)
        expect(node_with_asymmetric_padding, inputs=[x, W], outputs=[y_with_asymmetric_padding],
               name='test_conv_with_strides_and_asymmetric_padding')

    def test_averagepool_2d_precomputed_pads(self):  # type: () -> None
        """
        input_shape: [1, 1, 5, 5]
        output_shape: [1, 1, 5, 5]
        pad_shape: [4, 4] -> [2, 2, 2, 2] by axis
        """
        node = onnx.helper.make_node(
            'AveragePool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[5, 5],
            pads=[2, 2, 2, 2]

        )
        x = np.array([[[
            [1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10],
            [11, 12, 13, 14, 15],
            [16, 17, 18, 19, 20],
            [21, 22, 23, 24, 25],
        ]]]).astype(np.float32)
        y = np.array([[[[7, 7.5, 8, 8.5, 9],
                        [9.5, 10, 10.5, 11, 11.5],
                        [12, 12.5, 13, 13.5, 14],
                        [14.5, 15, 15.5, 16, 16.5],
                        [17, 17.5, 18, 18.5, 19]]]]).astype(np.float32)

        expect(node, inputs=[x], outputs=[y], name='test_averagepool_2d_precomputed_pads')

    def test_averagepool_2d_precomputed_strides(self):  # type: () -> None
        """
        input_shape: [1, 1, 5, 5]
        output_shape: [1, 1, 2, 2]
        """
        node = onnx.helper.make_node(
            'AveragePool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[2, 2],
            strides=[2, 2]
        )
        x = np.array([[[
            [1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10],
            [11, 12, 13, 14, 15],
            [16, 17, 18, 19, 20],
            [21, 22, 23, 24, 25],
        ]]]).astype(np.float32)
        y = np.array([[[[4, 6],
                        [14, 16]]]]).astype(np.float32)

        expect(node, inputs=[x], outputs=[y], name='test_averagepool_2d_precomputed_strides')


    def test_averagepool_2d_precomputed_same_upper(self):  # type: () -> None
        """
        input_shape: [1, 1, 5, 5]
        output_shape: [1, 1, 3, 3]
        pad_shape: [2, 2] -> [1, 1, 1, 1] by axis
        """
        node = onnx.helper.make_node(
            'AveragePool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[3, 3],
            strides=[2, 2],
            auto_pad='SAME_UPPER'
        )
        x = np.array([[[
            [1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10],
            [11, 12, 13, 14, 15],
            [16, 17, 18, 19, 20],
            [21, 22, 23, 24, 25],
        ]]]).astype(np.float32)
        y = np.array([[[[4, 5.5, 7],
                        [11.5, 13, 14.5],
                        [19, 20.5, 22]]]]).astype(np.float32)

        expect(node, inputs=[x], outputs=[y], name='test_averagepool_2d_precomputed_same_upper')


    def test_averagepool_2d_default(self):  # type: () -> None
        """
        input_shape: [1, 3, 32, 32]
        output_shape: [1, 3, 31, 31]
        """
        node = onnx.helper.make_node(
            'AveragePool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[2, 2],
        )
        x = np.random.randn(1, 3, 32, 32).astype(np.float32)
        x_shape = np.shape(x)
        kernel_shape = (2, 2)
        strides = (1, 1)
        out_shape = get_output_shape('VALID', x_shape[2:], kernel_shape, strides)
        padded = x
        y = pool(padded, x_shape, kernel_shape, strides, out_shape, (0, 0), 'AVG')

        expect(node, inputs=[x], outputs=[y], name='test_averagepool_2d_default')

    def test_averagepool_2d_pads(self):  # type: () -> None
        """
        input_shape: [1, 3, 28, 28]
        output_shape: [1, 3, 30, 30]
        pad_shape: [4, 4] -> [2, 2, 2, 2] by axis
        """
        node = onnx.helper.make_node(
            'AveragePool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[3, 3],
            pads=[2, 2, 2, 2]
        )
        x = np.random.randn(1, 3, 28, 28).astype(np.float32)
        x_shape = np.shape(x)
        kernel_shape = (3, 3)
        strides = (1, 1)
        pad_bottom = 2
        pad_top = 2
        pad_right = 2
        pad_left = 2
        pad_shape = [pad_top + pad_bottom, pad_left + pad_right]
        out_shape = get_output_shape('VALID', np.add(x_shape[2:], pad_shape), kernel_shape, strides)
        padded = np.pad(x, ((0, 0), (0, 0), (pad_top, pad_bottom), (pad_left, pad_right)), mode='constant',
                        constant_values=np.nan)
        y = pool(padded, x_shape, kernel_shape, strides, out_shape, pad_shape, 'AVG')

        expect(node, inputs=[x], outputs=[y], name='test_averagepool_2d_pads')

    def test_averagepool_2d_strides(self):  # type: () -> None
        """
        input_shape: [1, 3, 32, 32]
        output_shape: [1, 3, 10, 10]
        """
        node = onnx.helper.make_node(
            'AveragePool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[5, 5],
            strides=[3, 3]
        )
        x = np.random.randn(1, 3, 32, 32).astype(np.float32)
        x_shape = np.shape(x)
        kernel_shape = (5, 5)
        strides = (3, 3)
        out_shape = get_output_shape('VALID', x_shape[2:], kernel_shape, strides)
        padded = x
        y = pool(padded, x_shape, kernel_shape, strides, out_shape, (0, 0), 'AVG')

        expect(node, inputs=[x], outputs=[y], name='test_averagepool_2d_strides')

    def test_maxpool_2d_precomputed_pads(self):  # type: () -> None
        """
        input_shape: [1, 1, 5, 5]
        output_shape: [1, 1, 5, 5]
        pad_shape: [4, 4] -> [2, 2, 2, 2] by axis
        """
        node = onnx.helper.make_node(
            'MaxPool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[5, 5],
            pads=[2, 2, 2, 2]

        )
        x = np.array([[[
            [1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10],
            [11, 12, 13, 14, 15],
            [16, 17, 18, 19, 20],
            [21, 22, 23, 24, 25],
        ]]]).astype(np.float32)
        y = np.array([[[
            [13, 14, 15, 15, 15],
            [18, 19, 20, 20, 20],
            [23, 24, 25, 25, 25],
            [23, 24, 25, 25, 25],
            [23, 24, 25, 25, 25]]]]).astype(np.float32)

        expect(node, inputs=[x], outputs=[y], name='test_maxpool_2d_precomputed_pads')

    def test_maxpool_with_argmax_2d_precomputed_pads(self):  # type: () -> None
        """
        input_shape: [1, 1, 5, 5]
        output_shape: [1, 1, 5, 5]
        pad_shape: [4, 4] -> [2, 2, 2, 2] by axis
        """
        node = onnx.helper.make_node(
            'MaxPool',
            inputs=['x'],
            outputs=['y', 'z'],
            kernel_shape=[5, 5],
            pads=[2, 2, 2, 2]
        )
        x = np.array([[[
            [1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10],
            [11, 12, 13, 14, 15],
            [16, 17, 18, 19, 20],
            [21, 22, 23, 24, 25],
        ]]]).astype(np.float32)
        y = np.array([[[
            [13, 14, 15, 15, 15],
            [18, 19, 20, 20, 20],
            [23, 24, 25, 25, 25],
            [23, 24, 25, 25, 25],
            [23, 24, 25, 25, 25]]]]).astype(np.float32)
        z = np.array([[[
            [12, 13, 14, 14, 14],
            [17, 18, 19, 19, 19],
            [22, 23, 24, 24, 24],
            [22, 23, 24, 24, 24],
            [22, 23, 24, 24, 24]]]]).astype(np.int64)

        expect(node, inputs=[x], outputs=[y, z], name='test_maxpool_with_argmax_2d_precomputed_pads')

    def test_maxpool_2d_precomputed_strides(self):  # type: () -> None
        """
        input_shape: [1, 1, 5, 5]
        output_shape: [1, 1, 2, 2]
        """
        node = onnx.helper.make_node(
            'MaxPool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[2, 2],
            strides=[2, 2]
        )
        x = np.array([[[
            [1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10],
            [11, 12, 13, 14, 15],
            [16, 17, 18, 19, 20],
            [21, 22, 23, 24, 25],
        ]]]).astype(np.float32)
        y = np.array([[[[7, 9],
                        [17, 19]]]]).astype(np.float32)

        expect(node, inputs=[x], outputs=[y], name='test_maxpool_2d_precomputed_strides')

    def test_maxpool_with_argmax_2d_precomputed_strides(self):  # type: () -> None
        """
        input_shape: [1, 1, 5, 5]
        output_shape: [1, 1, 2, 2]
        """
        node = onnx.helper.make_node(
            'MaxPool',
            inputs=['x'],
            outputs=['y', 'z'],
            kernel_shape=[2, 2],
            strides=[2, 2],
            storage_order=1
        )
        x = np.array([[[
            [1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10],
            [11, 12, 13, 14, 15],
            [16, 17, 18, 19, 20],
            [21, 22, 23, 24, 25],
        ]]]).astype(np.float32)
        y = np.array([[[[7, 9],
                        [17, 19]]]]).astype(np.float32)
        z = np.array([[[[6, 16],
                        [8, 18]]]]).astype(np.int64)

        expect(node, inputs=[x], outputs=[y, z], name='test_maxpool_with_argmax_2d_precomputed_strides')

    def test_maxpool_2d_precomputed_same_upper(self):  # type: () -> None
        """
        input_shape: [1, 1, 5, 5]
        output_shape: [1, 1, 3, 3]
        pad_shape: [2, 2] -> [1, 1, 1, 1] by axis
        """
        node = onnx.helper.make_node(
            'MaxPool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[3, 3],
            strides=[2, 2],
            auto_pad='SAME_UPPER'
        )
        x = np.array([[[
            [1, 2, 3, 4, 5],
            [6, 7, 8, 9, 10],
            [11, 12, 13, 14, 15],
            [16, 17, 18, 19, 20],
            [21, 22, 23, 24, 25],
        ]]]).astype(np.float32)
        y = np.array([[[[7, 9, 10],
                        [17, 19, 20],
                        [22, 24, 25]]]]).astype(np.float32)

        expect(node, inputs=[x], outputs=[y], name='test_maxpool_2d_precomputed_same_upper')

    def test_maxpool_2d_default(self):  # type: () -> None
        """
        input_shape: [1, 3, 32, 32]
        output_shape: [1, 3, 31, 31]
        """
        node = onnx.helper.make_node(
            'MaxPool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[2, 2],
        )
        x = np.random.randn(1, 3, 32, 32).astype(np.float32)
        x_shape = np.shape(x)
        kernel_shape = (2, 2)
        strides = (1, 1)
        out_shape = get_output_shape('VALID', x_shape[2:], kernel_shape, strides)
        padded = x
        y = pool(padded, x_shape, kernel_shape, strides, out_shape, (0, 0), 'MAX')

        expect(node, inputs=[x], outputs=[y], name='test_maxpool_2d_default')

    def test_maxpool_2d_pads(self):  # type: () -> None
        """
        input_shape: [1, 3, 28, 28]
        output_shape: [1, 3, 30, 30]
        pad_shape: [4, 4] -> [2, 2, 2, 2] by axis
        """
        node = onnx.helper.make_node(
            'MaxPool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[3, 3],
            pads=[2, 2, 2, 2]
        )
        x = np.random.randn(1, 3, 28, 28).astype(np.float32)
        x_shape = np.shape(x)
        kernel_shape = (3, 3)
        strides = (1, 1)
        pad_bottom = pad_top = pad_right = pad_left = 2
        pad_shape = [pad_top + pad_bottom, pad_left + pad_right]
        out_shape = get_output_shape('VALID', np.add(x_shape[2:], pad_shape), kernel_shape, strides)
        padded = np.pad(x, ((0, 0), (0, 0), (pad_top, pad_bottom), (pad_left, pad_right)), mode='constant',
                        constant_values=np.nan)
        y = pool(padded, x_shape, kernel_shape, strides, out_shape, pad_shape, 'MAX')

        expect(node, inputs=[x], outputs=[y], name='test_maxpool_2d_pads')

    def test_maxpool_2d_strides(self):  # type: () -> None
        """
        input_shape: [1, 3, 32, 32]
        output_shape: [1, 3, 10, 10]
        """
        node = onnx.helper.make_node(
            'MaxPool',
            inputs=['x'],
            outputs=['y'],
            kernel_shape=[5, 5],
            strides=[3, 3]
        )
        x = np.random.randn(1, 3, 32, 32).astype(np.float32)
        x_shape = np.shape(x)
        kernel_shape = (5, 5)
        strides = (3, 3)
        out_shape = get_output_shape('VALID', x_shape[2:], kernel_shape, strides)
        padded = x
        y = pool(padded, x_shape, kernel_shape, strides, out_shape, (0, 0), 'MAX')

        expect(node, inputs=[x], outputs=[y], name='test_maxpool_2d_strides')

    # def test_batchnorm(self):  # type: () -> None
    #     def _batchnorm_test_mode(x, s, bias, mean, var, epsilon=1e-5):  # type: ignore
    #         dims_x = len(x.shape)
    #         dim_ones = (1,) * (dims_x - 2)
    #         s = s.reshape(-1, *dim_ones)
    #         bias = bias.reshape(-1, *dim_ones)
    #         mean = mean.reshape(-1, *dim_ones)
    #         var = var.reshape(-1, *dim_ones)
    #         return s * (x - mean) / np.sqrt(var + epsilon) + bias

    #     def _batchnorm_forward(X, gamma, beta, mu, var, epsilon=1e-5):
    #         n_X, c_X, h_X, w_X = X.shape
    #         X_flat = X.reshape(n_X, c_X*h_X*w_X)

    #         # mu = np.mean(X_flat, axis=0)
    #         # var = np.var(X_flat, axis=0)
    #         X_norm = (X_flat - mu)/np.sqrt(var + epsilon)

    #         out = gamma * X_norm + beta
    #         return out

    #     # input size: (1, 2, 1, 3)
    #     x = np.random.randn(1, 3, 3, 3).astype(np.float32)
    #     n_X, c_X, h_X, w_X = x.shape
    #     X_flat = x.reshape(n_X, c_X*h_X*w_X)
    #     s = np.random.randn(*X_flat.shape).astype(np.float32)
    #     bias = np.random.randn(*X_flat.shape).astype(np.float32)
    #     mean = np.mean(X_flat, axis=0)
    #     var = np.var(X_flat, axis=0)
    #     y = s * (X_flat - mean)/np.sqrt(var + 1e-5) + bias
    #     y = y.reshape(x.shape)

        
    #     x_t = tensor.from_numpy(x)
    #     x_t.to_device(gpu_dev)
    #     s_t = tensor.from_numpy(s)
    #     s_t.to_device(gpu_dev)
    #     bias_t = tensor.from_numpy(bias)
    #     bias_t.to_device(gpu_dev)
    #     mean_t = tensor.from_numpy(mean)
    #     mean_t.to_device(gpu_dev)
    #     var_t = tensor.from_numpy(var)
    #     var_t.to_device(gpu_dev)

    #     handle = singa.CudnnBatchNormHandle(0.9, x_t.data)
    #     y_t = autograd.batchnorm_2d(handle, x_t, s_t, bias_t, mean_t, var_t)
    #     print(y)
    #     print(tensor.to_numpy(y_t))
    #     node = onnx.helper.make_node(
    #         'BatchNormalization',
    #         inputs=['x', 'scale', 'B', 'mean', 'var'],
    #         outputs=['y'],
    #     )

    #     # output size: (1, 2, 1, 3)
    #     expect(node, inputs=[x, s, bias, mean, var], outputs=[y],
    #            name='test_batchnorm_example')

    #     # input size: (2, 3, 4, 5)
    #     x = np.random.randn(2, 3, 4, 5).astype(np.float32)
    #     s = np.random.randn(3).astype(np.float32)
    #     bias = np.random.randn(3).astype(np.float32)
    #     mean = np.random.randn(3).astype(np.float32)
    #     var = np.random.rand(3).astype(np.float32)
    #     epsilon = 1e-2
    #     y = _batchnorm_test_mode(x, s, bias, mean, var, epsilon).astype(np.float32)

    #     node = onnx.helper.make_node(
    #         'BatchNormalization',
    #         inputs=['x', 's', 'bias', 'mean', 'var'],
    #         outputs=['y'],
    #         epsilon=epsilon,
    #     )

    #     # output size: (2, 3, 4, 5)
    #     expect(node, inputs=[x, s, bias, mean, var], outputs=[y],
    #            name='test_batchnorm_epsilon')

    
    # def test_reshape(self):  # type: () -> None
    #     original_shape = [2, 3, 4]
    #     test_cases = {
    #         'reordered_dims': np.array([4, 2, 3], dtype=np.int64),
    #         'reduced_dims': np.array([3, 8], dtype=np.int64),
    #         'extended_dims': np.array([3, 2, 2, 2], dtype=np.int64),
    #         'one_dim': np.array([24], dtype=np.int64),
    #         'negative_dim': np.array([6, -1, 2], dtype=np.int64),
    #     }
    #     data = np.random.random_sample(original_shape).astype(np.float32)

    #     for test_name, shape in test_cases.items():
    #         node = onnx.helper.make_node(
    #             'Reshape',
    #             inputs=['data', 'shape'],
    #             outputs=['reshaped'],
    #         )

    #         reshaped = np.reshape(data, shape)
    #         expect(node, inputs=[data, shape], outputs=[reshaped],
    #                name='test_reshape_' + test_name)

    def test_concat(self):  # type: () -> None
        test_cases = {
            # '1d': ([1, 2], not support 1d
                #    [3, 4]),
            '2d': ([[1, 2], [3, 4]],
                   [[5, 6], [7, 8]]),
            '3d': ([[[1, 2], [3, 4]], [[5, 6], [7, 8]]],
                   [[[9, 10], [11, 12]], [[13, 14], [15, 16]]])
        }  # type: Dict[Text, Sequence[Any]]

        for test_case, values_ in test_cases.items():
            values = [np.asarray(v, dtype=np.float32) for v in values_]
            for i in range(len(values[0].shape)):
                in_args = ['value' + str(k) for k in range(len(values))]
                node = onnx.helper.make_node(
                    'Concat',
                    inputs=[s for s in in_args],
                    outputs=['output'],
                    axis=i
                )
                output = np.concatenate(values, i)
                expect(node, inputs=[v for v in values], outputs=[output],
                       name='test_concat_' + test_case + '_axis_' + str(i))

            for i in range(-len(values[0].shape), 0):
                in_args = ['value' + str(k) for k in range(len(values))]
                node = onnx.helper.make_node(
                    'Concat',
                    inputs=[s for s in in_args],
                    outputs=['output'],
                    axis=i
                )
                output = np.concatenate(values, i)
                expect(node, inputs=[v for v in values], outputs=[output],
                       name='test_concat_' + test_case + '_axis_negative_' + str(abs(i)))

    # def test_flatten(self):  # type: () -> None
    #     shape = (2, 3, 4, 5)
    #     a = np.random.random_sample(shape).astype(np.float32)

    #     for i in range(len(shape)):
    #         node = onnx.helper.make_node(
    #             'Flatten',
    #             inputs=['a'],
    #             outputs=['b'],
    #             axis=i,
    #         )

    #         new_shape = (1, -1) if i == 0 else (np.prod(shape[0:i]).astype(int), -1)
    #         b = np.reshape(a, new_shape)
    #         expect(node, inputs=[a], outputs=[b],
    #                name='test_flatten_axis' + str(i))

    # def test_flatten_with_default_axis(self):  # type: () -> None
    #     node = onnx.helper.make_node(
    #         'Flatten',
    #         inputs=['a'],
    #         outputs=['b'],  # Default value for axis: axis=1
    #     )

    #     shape = (5, 4, 3, 2)
    #     a = np.random.random_sample(shape).astype(np.float32)
    #     new_shape = (5, 24)
    #     b = np.reshape(a, new_shape)
    #     expect(node, inputs=[a], outputs=[b],
    #            name='test_flatten_default_axis')

    # def test_flatten_negative_axis(self):  # type: () -> None
    #     shape = (2, 3, 4, 5)
    #     a = np.random.random_sample(shape).astype(np.float32)

    #     for i in range(-len(shape), 0):
    #         node = onnx.helper.make_node(
    #             'Flatten',
    #             inputs=['a'],
    #             outputs=['b'],
    #             axis=i,
    #         )

    #         new_shape = (np.prod(shape[0:i]).astype(int), -1)
    #         b = np.reshape(a, new_shape)
    #         expect(node, inputs=[a], outputs=[b],
    #                name='test_flatten_negative_axis' + str(abs(i)))


    def test_add(self):  # type: () -> None
        node = onnx.helper.make_node(
            'Add',
            inputs=['x', 'y'],
            outputs=['sum'],
        )

        x = np.random.randn(3, 4, 5).astype(np.float32)
        y = np.random.randn(3, 4, 5).astype(np.float32)
        expect(node, inputs=[x, y], outputs=[x + y],
               name='test_add')

    def test_add_broadcast(self):  # type: () -> None
        node = onnx.helper.make_node(
            'Add',
            inputs=['x', 'y'],
            outputs=['sum'],
        )

        x = np.random.randn(3, 4, 5).astype(np.float32)
        y = np.random.randn(5).astype(np.float32)
        expect(node, inputs=[x, y], outputs=[x + y],
               name='test_add_bcast')

    def test_sum(self):  # type: () -> None
        data_0 = np.array([3, 0, 2]).astype(np.float32)
        data_1 = np.array([1, 3, 4]).astype(np.float32)
        data_2 = np.array([2, 6, 6]).astype(np.float32)
        result = np.array([6, 9, 12]).astype(np.float32)
        node = onnx.helper.make_node(
            'Sum',
            inputs=['data_0', 'data_1', 'data_2'],
            outputs=['result'],
        )
        expect(node, inputs=[data_0, data_1, data_2], outputs=[result],
               name='test_sum_example')

        node = onnx.helper.make_node(
            'Sum',
            inputs=['data_0'],
            outputs=['result'],
        )
        expect(node, inputs=[data_0], outputs=[data_0],
               name='test_sum_one_input')

        result = np.add(data_0, data_1)
        node = onnx.helper.make_node(
            'Sum',
            inputs=['data_0', 'data_1'],
            outputs=['result'],
        )
        expect(node, inputs=[data_0, data_1], outputs=[result],
               name='test_sum_two_inputs')

# return padding shape of conv2d or pooling
def get_pad_shape(auto_pad,  # type: Text
                  input_spatial_shape,  # type: Sequence[int]
                  kernel_spatial_shape,  # type: Sequence[int]
                  strides_spatial,  # type: Sequence[int]
                  output_spatial_shape  # type: Sequence[int]
                  ):  # type: (...) -> Sequence[int]
    pad_shape = [0] * len(input_spatial_shape)
    if auto_pad in ('SAME_UPPER', 'SAME_LOWER'):
        for i in range(len(input_spatial_shape)):
            pad_shape[i] = (output_spatial_shape[i] - 1) * strides_spatial[i] + \
                kernel_spatial_shape[i] - input_spatial_shape[i]
    elif auto_pad == 'VALID':
        pass
    return pad_shape

# return output shape of conv2d or pooling
def get_output_shape(auto_pad,  # type: Text
                     input_spatial_shape,  # type: Sequence[int]
                     kernel_spatial_shape,  # type: Sequence[int]
                     strides_spatial  # type: Sequence[int]
                     ):  # type: (...) -> Sequence[int]
    out_shape = [0] * len(input_spatial_shape)
    if auto_pad in ('SAME_UPPER', 'SAME_LOWER'):
        for i in range(len(input_spatial_shape)):
            out_shape[i] = int(
                np.ceil(
                    float(
                        input_spatial_shape[i])
                    / float(
                        strides_spatial[i])))
    elif auto_pad == 'VALID':
        for i in range(len(input_spatial_shape)):
            out_shape[i] = int(np.ceil(float(input_spatial_shape[i] - (kernel_spatial_shape[i] - 1)) / float(strides_spatial[i])))
    return out_shape


def pool(padded,  # type: np.ndarray
         x_shape,  # type: Sequence[int]
         kernel_shape,  # type: Sequence[int]
         strides_shape,  # type: Sequence[int]
         out_shape,  # type: Sequence[int]
         pad_shape,  # type: Sequence[int]
         pooling_type,  # type: Text
         count_include_pad=0  # type: int
         ):  # type: (...) -> np.ndarray
    spatial_size = len(x_shape) - 2
    y = np.zeros([x_shape[0], x_shape[1]] + list(out_shape))

    for shape in itertools.product(range(x_shape[0]), range(x_shape[1]), *[range(int(
            (x_shape[i + 2] + pad_shape[i] - kernel_shape[i]) / strides_shape[i] + 1)) for i in range(spatial_size)]):
        window = padded[shape[0], shape[1]]
        window_vals = np.array([window[i] for i in list(
            itertools.product(
                *[range(strides_shape[i] * shape[i + 2], strides_shape[i] * shape[i + 2] + kernel_shape[i]) for i in
                  range(spatial_size)])
        )])
        if pooling_type == 'AVG':
            f = np.average
        elif pooling_type == 'MAX':
            f = np.max
        else:
            raise NotImplementedError(
                'Pooling type {} does not support. Should be AVG, MAX'.format(pooling_type))

        if count_include_pad == 1 and pooling_type == 'AVG':
            y[shape] = f(window_vals)
        else:
            y[shape] = f(window_vals[np.where(~np.isnan(window_vals))])
    return y.astype(np.float32)

if __name__ == '__main__':
    unittest.main()
