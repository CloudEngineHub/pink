#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 Stéphane Caron

"""General description"""

from typing import Callable, Optional, Tuple, Union

import numpy as np

from ..configuration import Configuration
from .barrier import CBF


class PositionCBF(CBF):
    r"""Abstract class description.

    Attributes:
        ...
    """

    frame: str
    p_min: Optional[np.ndarray]
    p_max: Optional[np.ndarray]
    mask: Optional[np.ndarray]

    def __init__(
        self,
        frame: str,
        mask: Optional[np.ndarray] = None,
        min: Optional[np.ndarray] = None,
        max: Optional[np.ndarray] = None,
        gain: float = 1.0,
    ):
        # TODO: define safe control?
        """..."""
        super().__init__(
            gain=gain,
            class_k_fn=lambda h: 1 / (1 + np.linalg.norm(h)),
        )

        self.mask = mask
        self.p_min = min
        self.p_max = max
        self.dim = 0

        if min is not None:
            self.dim += 3
        if max is not None:
            self.dim += 3

    def compute_barrier(self, configuration: Configuration) -> np.ndarray:
        """..."""
        pos_world = configuration.get_transform_frame_to_world(self.frame).translation
        tasks = []
        if min is not None:
            tasks.append(pos_world - self.p_min)
        if max is not None:
            tasks.append(self.p_max - pos_world)
        return np.concatenate(tasks)

    def compute_jacobian(self, configuration: Configuration) -> np.ndarray:
        """..."""
        pos_jac = configuration.get_frame_jacobian(self.frame)[:3]
        jacobian = []
        if min is not None:
            jacobian.append(pos_jac.copy())
        if max is not None:
            jacobian.append(-pos_jac.copy())

        return np.hstack(jacobian)
