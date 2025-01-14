# =========================================================================
# Copyright (C) 2023. Huawei Technologies Co., Ltd. All rights reserved.
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
# =========================================================================


import torch
from torch import nn
import h5py
import os
import numpy as np


class PretrainedEmbedding(nn.Module):
    def __init__(self,
                 feature_name,
                 feature_spec,
                 pretrained_path,
                 embedding_dim,
                 pretrain_dim,
                 pretrain_usage="init"):
        """
        Fusion pretrained embedding with ID embedding
        :param: fusion_type: init/sum/concat
        """
        super().__init__()
        assert pretrain_usage in ["init", "sum", "concat"]
        self.pretrain_usage = pretrain_usage
        padding_idx = feature_spec.get("padding_idx", None)
        embedding_matrix = nn.Embedding(feature_spec["vocab_size"],
                                        pretrain_dim,
                                        padding_idx=padding_idx)
        self.pretrain_embedding = self.load_pretrained_embedding(embedding_matrix,
                                                                 pretrained_path,
                                                                 feature_name,
                                                                 freeze=feature_spec["freeze_emb"],
                                                                 padding_idx=padding_idx)
        if pretrain_usage != "init":
            self.id_embedding = nn.Embedding(feature_spec["vocab_size"],
                                             embedding_dim,
                                             padding_idx=padding_idx)
        if pretrain_usage == "sum" and embedding_dim != pretrain_dim:
            self.proj_1 = nn.Linear(pretrain_dim, embedding_dim)
        else:
            self.proj_1 = None
        if pretrain_usage == "concat":
            self.proj_2 = nn.Linear(pretrain_dim + embedding_dim, embedding_dim)

    def get_pretrained_embedding(self, pretrained_path, feature_name):
        with h5py.File(pretrained_path, 'r') as hf:
            embeddings = hf[feature_name][:]
        return embeddings

    def load_pretrained_embedding(self, embedding_matrix, pretrained_path, feature_name, freeze=False, padding_idx=None):
        embeddings = self.get_pretrained_embedding(pretrained_path, feature_name)
        if padding_idx is not None:
            embeddings[padding_idx] = np.zeros(embeddings.shape[-1])
        assert embeddings.shape[-1] == embedding_matrix.embedding_dim, \
            "{}\'s pretrain_dim is not correct.".format(feature_name)
        embeddings = torch.from_numpy(embeddings).float()
        embedding_matrix.weight = torch.nn.Parameter(embeddings)
        if freeze:
            embedding_matrix.weight.requires_grad = False
        return embedding_matrix

    def forward(self, inputs):
        pretrain_emb = self.pretrain_embedding(inputs)
        if self.pretrain_usage == "init":
            feature_emb = pretrain_emb
        else:
            id_emb = self.id_embedding(inputs)
            if self.pretrain_usage == "sum":
                if self.proj_1 is not None:
                    feature_emb = self.proj_1(pretrain_emb) + id_emb
                else:
                    feature_emb = pretrain_emb + id_emb
            if self.pretrain_usage == "concat":
                feature_emb = torch.cat([pretrain_emb, id_emb], dim=-1)
                feature_emb = self.proj_2(feature_emb)
        return feature_emb
