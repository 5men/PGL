# Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
    Deepwalk model file.
"""
import math

import paddle
import paddle.nn as nn
import paddle.nn.functional as F


class SkipGramModel(nn.Layer):
    def __init__(self,
                 num_nodes,
                 embed_size=16,
                 neg_num=5,
                 num_emb_part=1,
                 sparse=False,
                 sparse_embedding=False,
                 shared_embedding=False):
        super(SkipGramModel, self).__init__()

        self.num_nodes = num_nodes
        self.neg_num = neg_num
        self.shared_embedding = shared_embedding

        # embed_init = nn.initializer.Uniform(
        # low=-1. / math.sqrt(embed_size), high=1. / math.sqrt(embed_size))
        u_embed_init = nn.initializer.Uniform(low=-1.0, high=1.0)
        u_emb_attr = paddle.ParamAttr(
            name="u_node_embedding", initializer=u_embed_init)

        v_embed_init = nn.initializer.Uniform(low=-1e-8, high=1e-8)
        v_emb_attr = paddle.ParamAttr(
            name="v_node_embedding", initializer=v_embed_init)

        if sparse_embedding:

            def u_emb_func(x):
                d_shape = paddle.shape(x)
                x_emb = paddle.static.nn.sparse_embedding(
                    paddle.reshape(x, [-1, 1]), [num_nodes, embed_size],
                    param_attr=u_emb_attr)
                return paddle.reshape(x_emb,
                                      [d_shape[0], d_shape[1], embed_size])
            def v_emb_func(x):
                d_shape = paddle.shape(x)
                x_emb = paddle.static.nn.sparse_embedding(
                    paddle.reshape(x, [-1, 1]), [num_nodes, embed_size],
                    param_attr=v_emb_attr)
                return paddle.reshape(x_emb,
                                      [d_shape[0], d_shape[1], embed_size])
            self.u_emb = u_emb_func
            self.v_emb = v_emb_func
        elif num_emb_part > 1:
            assert embed_size % num_emb_part == 0
            u_emb_list, v_emb_list = [], []
            for i in range(num_emb_part):
                u_emb_attr = paddle.ParamAttr(
                    name="u_node_embedding_part%s" % i, initializer=u_embed_init)
                u_emb = nn.Embedding(
                    num_nodes,
                    embed_size // num_emb_part,
                    weight_attr=u_emb_attr)
                u_emb_list.append(u_emb)
                v_emb_attr = paddle.ParamAttr(
                    name="v_node_embedding_part%s" % i, initializer=v_embed_init)
                v_emb = nn.Embedding(
                    num_nodes,
                    embed_size // num_emb_part,
                    weight_attr=v_emb_attr)
                v_emb_list.append(v_emb)
            self.u_emb_list = nn.LayerList(u_emb_list)
            self.u_emb = lambda x: paddle.concat([emb(x) for emb in u_emb_list], -1)
            self.v_emb_list = nn.LayerList(v_emb_list)
            self.v_emb = lambda x: paddle.concat([emb(x) for emb in v_emb_list], -1)
        else:
            self.u_emb = nn.Embedding(
                num_nodes, embed_size, sparse=sparse, weight_attr=u_emb_attr)
            self.v_emb = nn.Embedding(
                num_nodes, embed_size, sparse=sparse, weight_attr=v_emb_attr)
        self.loss = paddle.nn.BCEWithLogitsLoss()

    def forward(self, src, dsts):
        # src [b, 1]
        # dsts [b, 1+neg]

        src_embed = self.u_emb(src)
        if self.shared_embedding:
            dsts_embed = self.u_emb(dsts)
        else:
            dsts_embed = self.v_emb(dsts)

        pos_embed = dsts_embed[:, 0:1]
        neg_embed = dsts_embed[:, 1:]

        pos_logits = paddle.matmul(
            src_embed, pos_embed, transpose_y=True)  # [batch_size, 1, 1]

        neg_logits = paddle.matmul(
            src_embed, neg_embed, transpose_y=True)  # [batch_size, 1, neg_num]

        ones_label = paddle.ones_like(pos_logits)
        pos_loss = self.loss(pos_logits, ones_label)

        zeros_label = paddle.zeros_like(neg_logits)
        neg_loss = self.loss(neg_logits, zeros_label)

        loss = (pos_loss + neg_loss) / 2
        return loss
