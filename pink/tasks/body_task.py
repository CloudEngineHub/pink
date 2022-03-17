#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 Stéphane Caron.
#
# This file is part of Pink.
#
# Pink is free software: you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation, either version 3 of the License, or (at your option) any
# later version.
#
# Pink is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU Lesser General Public License for more
# details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with Pink. If not, see <http://www.gnu.org/licenses/>.

"""
Body task specification.
"""

from typing import Optional, Sequence, Tuple, Union

import numpy as np
import pinocchio as pin

from ..configured_robot import ConfiguredRobot
from .exceptions import TargetNotSet
from .task import Task
from .utils import body_box_minus


class BodyTask(Task):

    """
    Regulate the pose of a robot body in the world frame.

    Attributes:
        body: Body frame name, typically the link name from the URDF.
        cost: 6D vector that specifies how much each coordinate (in the local
            body frame) contributes to the cost. Position costs come first
            (Pinocchio spatial vector convention) and are in
            :math:`[\\mathrm{cost}] / [\\mathrm{m}]`, where the the unit of
            :math:`[\\mathrm{cost}]` up to the user. They are followed by
            orientation costs in :math:`[\\mathrm{cost}] / [\\mathrm{rad}]`.
            Set a cost to zero to disable the task along a coordinate (no cost
            no effect).
        error_in_body: task error in body frame at the last time it was
            evaluated.
        lm_damping: Unitless scale of the Levenberg-Marquardt (only when
            the error is large) regularization term, which helps when
            targets are unfeasible. Increase this value if the task is too
            jerky under unfeasible targets, but beware that a larger
            damping slows down the task.
        transform_target_to_world: Target pose for the body frame.

    Costs are designed so that position/orientation costs can be compared
    between tasks. For example, if task 1 has a position cost of 1.0 and task 2
    a position cost of 0.1, then a 1 [cm] error in task 1 costs as much as a 10
    [cm] error in task 2.

    Note:
        Dimensionally, the 6D cost vector is a (normalized) force screw and our
        objective function is a (normalized) energy.
    """

    body: str
    cost: np.ndarray
    error_in_body: np.ndarray
    lm_damping: float
    transform_target_to_world: Optional[pin.SE3]

    def __init__(
        self,
        body: str,
        position_cost: Union[float, Sequence[float]],
        orientation_cost: Union[float, Sequence[float]],
        lm_damping: float = 1e-6,
    ) -> None:
        """
        Define a new body task.

        Args:
            body: Name of the body frame to move to the target pose.
            position_cost: Contribution of position errors to the normalized
                cost, in :math:`[\\mathrm{cost}] / [\\mathrm{m}]`. If this is a
                vector, the cost is anisotropic and each coordinate corresponds
                to an axis in the local body frame.
            orientation_cost: Contribution of orientation errors to the
                normalized cost, in :math:`[\\mathrm{cost}] / [\\mathrm{rad}]`.
                If this is a vector, the cost is anisotropic and each
                coordinate corresponds to an axis in the local body frame.
            lm_damping: Levenberg-Marquardt damping (see class attributes). The
                default value is conservatively low.
        """
        self.body = body
        self.cost = np.ones(6)
        self.error_in_body = np.zeros(6)
        self.lm_damping = lm_damping
        self.transform_target_to_world = None
        #
        self.set_position_cost(position_cost)
        self.set_orientation_cost(orientation_cost)

    def set_position_cost(
        self, position_cost: Union[float, Sequence[float]]
    ) -> None:
        """
        Set a new cost for all 3D position coordinates.

        Args:
            position_cost: Contribution of position errors to the normalized
                cost, in :math:`[\\mathrm{cost}] / [\\mathrm{m}]`. If this is a
                vector, the cost is anisotropic and each coordinate corresponds
                to an axis in the local body frame.
        """
        if isinstance(position_cost, float):
            assert position_cost >= 0.0
        else:  # not isinstance(position_cost, float)
            assert all(cost >= 0.0 for cost in position_cost)
        self.cost[0:3] = position_cost

    def set_orientation_cost(
        self, orientation_cost: Union[float, Sequence[float]]
    ) -> None:
        """
        Set a new cost for all 3D orientation coordinates.

        Args:
            orientation_cost: Contribution of orientation errors to the
                normalized cost, in :math:`[\\mathrm{cost}] / [\\mathrm{rad}]`.
                If this is a vector, the cost is anisotropic and each
                coordinate corresponds to an axis in the local body frame.
        """
        if isinstance(orientation_cost, float):
            assert orientation_cost >= 0.0
        else:  # not isinstance(orientation_cost, float)
            assert all(cost >= 0.0 for cost in orientation_cost)
        self.cost[3:6] = orientation_cost

    def set_target(
        self,
        transform_target_to_world: pin.SE3,
    ) -> None:
        """
        Set task target pose in the world frame.

        Args:
            transform_target_to_world: Transform from the task target frame to
                the world frame.
        """
        self.transform_target_to_world = transform_target_to_world.copy()

    def compute_error_in_body(self, robot: ConfiguredRobot) -> np.ndarray:
        """
        Compute the body twist error, that is, the (box minus) difference
        between target and current body configuration.

        Args:
            robot: Robot model and current configuration to read values from.

        Returns:
            Coordinate vector of the body twist error.
        """
        if self.transform_target_to_world is None:
            raise TargetNotSet(f"no target set for body {self.body}")
        transform_body_to_world = robot.get_transform_body_to_world(self.body)
        error_in_body: np.ndarray = -body_box_minus(
            self.transform_target_to_world,
            transform_body_to_world,
        )
        self.error_in_body = error_in_body
        return error_in_body

    def compute_task_dynamics(
        self, robot: ConfiguredRobot
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute the matrix :math:`J(q)` and vector :math:`\\alpha e(q)` such
        that the task dynamics are:

        .. math::

            J(q) \\Delta q = \\alpha e(q)

        The Jacobian matrix is :math:`J(q) \\in \\mathbb{R}^{6 \\times n}`,
        with :math:`n` the dimension of the robot's tangent space, and the
        error vector is :math:`e(q) \\in \\mathbb{R}^6`. See
        [`Task.compute_task_dynamics`][.tasks.task.Task.compute_task_dynamics]
        for more documentation.

        Args:
            robot: Robot model and current configuration to read values from.

        Returns:
            Pair :math:`(J, \\alpha e)` of Jacobian matrix and error vector,
            both expressed in the body frame.
        """
        jacobian_in_body = robot.get_body_jacobian(self.body)
        error_in_body = self.compute_error_in_body(robot)
        return jacobian_in_body, self.gain * error_in_body

    def compute_qp_objective(
        self, robot: pin.RobotWrapper
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute the Hessian matrix :math:`H` and linear vector :math:`c` such
        that the contribution of the task to the QP objective is:

        \\[
            \\| J \\Delta q - \\alpha e \\|_{W}^2
            = \\frac{1}{2} \\Delta q^T H \\Delta q + c^T q
        \\]

        The weight matrix :math:`W \\in \\mathbb{R}^{6 \\times 6}` combines
        position and orientation costs. The unit of the overall contribution is
        [cost]^2. The configuration displacement :math:`\\Delta q` is the
        output of inverse kinematics (we divide it by :math:`\\Delta t` to get
        a commanded velocity).

        Args:
            robot: Robot model and configuration.

        Returns:
            Pair :math:`(H, c)` of Hessian matrix and linear vector of the QP
            objective.

        See also:
            Levenberg-Marquardt damping is described in
            "Solvability-Unconcerned Inverse Kinematics by the
            Levenberg-Marquardt Method" (Sugihara, 2011). The dimensional
            analysis in this class is our own.
        """
        jacobian, error = self.compute_task_dynamics(robot)
        weight = np.diag(self.cost)  # [cost] * [twist]^{-1}
        weighted_jacobian = weight @ jacobian  # [cost]
        weighted_error = weight @ error  # [cost]
        mu = self.lm_damping * weighted_error @ weighted_error  # [cost]^2
        eye_tg = np.eye(robot.nv)
        # Our Levenberg-Marquardt damping `mu * eye_tg` is isotropic in the
        # robot's tangent space. If it helps we can add a tangent-space scaling
        # to damp the floating base differently from joint angular velocities.
        H = weighted_jacobian.T @ weighted_jacobian + mu * eye_tg
        c = -weighted_error.T @ weighted_jacobian
        return (H, c)

    def __repr__(self):
        """
        Human-readable representation of the task.
        """
        return (
            f"BodyTask({self.body}, "
            f"gain={self.gain}, "
            f"orientation_cost={self.cost[3:6]}, "
            f"position_cost={self.cost[0:3]}, "
            f"target={self.transform_target_to_world})"
        )