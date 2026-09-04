"""
Particle Swarm Optimization (PSO) Continuous Strategy Parameter Tuning.
Models swarm intelligence dynamics to discover global optima across non-convex parameter surfaces.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
import random
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np

logger = logging.getLogger("autotrade.optimizer.pso_optimizer")


@dataclass
class Particle:
    """Represents a particle exploring the multidimensional parameter search space."""
    position: Dict[str, float]
    velocity: Dict[str, float]
    best_position: Dict[str, float] = field(default_factory=dict)
    best_fitness: float = -999.0
    current_fitness: float = -999.0


class ParticleSwarmOptimizer:
    """
    Particle Swarm Optimization (PSO) Engine.
    Features inertia weight damping and stochastic acceleration coefficients.
    """
    def __init__(
        self,
        param_bounds: Dict[str, Tuple[float, float, str]],
        swarm_size: int = 20,
        max_iterations: int = 10,
        inertia_weight: float = 0.72,
        cognitive_coeff: float = 1.49,
        social_coeff: float = 1.49
    ):
        self.param_bounds = param_bounds
        self.swarm_size = swarm_size
        self.max_iterations = max_iterations
        self.w = inertia_weight
        self.c1 = cognitive_coeff
        self.c2 = social_coeff

    def optimize(
        self,
        fitness_fn: Callable[[Dict[str, Any]], float]
    ) -> Dict[str, Any]:
        """
        Executes PSO optimization over parameter bounds.
        `fitness_fn(params_dict)` returns scalar objective score (e.g. Sharpe ratio).
        """
        particles: List[Particle] = []
        gbest_position: Dict[str, float] = {}
        gbest_fitness: float = -9999.0

        # Initialize Swarm
        for _ in range(self.swarm_size):
            pos = {}
            vel = {}
            for k, (p_min, p_max, _) in self.param_bounds.items():
                pos[k] = random.uniform(float(p_min), float(p_max))
                span = float(p_max) - float(p_min)
                vel[k] = random.uniform(-span * 0.1, span * 0.1)

            part = Particle(position=pos, velocity=vel, best_position=dict(pos))
            particles.append(part)

        # Iteration Loop
        for it in range(self.max_iterations):
            for part in particles:
                # Convert to bounded typed parameters
                eval_params = self._format_params(part.position)
                fitness = fitness_fn(eval_params)
                part.current_fitness = fitness

                # Update personal best
                if fitness > part.best_fitness:
                    part.best_fitness = fitness
                    part.best_position = dict(part.position)

                # Update global best
                if fitness > gbest_fitness:
                    gbest_fitness = fitness
                    gbest_position = dict(part.position)

            # Update Velocities and Positions
            for part in particles:
                for k, (p_min, p_max, _) in self.param_bounds.items():
                    r1 = random.random()
                    r2 = random.random()
                    
                    # Velocity equation
                    cog = self.c1 * r1 * (part.best_position[k] - part.position[k])
                    soc = self.c2 * r2 * (gbest_position[k] - part.position[k])
                    part.velocity[k] = self.w * part.velocity[k] + cog + soc
                    
                    # Position update with boundary clamping
                    new_pos = part.position[k] + part.velocity[k]
                    part.position[k] = max(float(p_min), min(float(p_max), new_pos))

            logger.info(f"PSO Iteration {it + 1}/{self.max_iterations} | Global Best Fitness: {gbest_fitness:.2f}")

        return {
            "best_parameters": self._format_params(gbest_position),
            "best_fitness": round(gbest_fitness, 3),
            "iterations_completed": self.max_iterations
        }

    def _format_params(self, raw_pos: Dict[str, float]) -> Dict[str, Any]:
        """Casts floating positions into integer or rounded float format based on schema."""
        out = {}
        for k, val in raw_pos.items():
            p_min, p_max, p_type = self.param_bounds[k]
            if p_type == "int":
                out[k] = int(round(val))
            else:
                out[k] = round(val, 4)
        return out
