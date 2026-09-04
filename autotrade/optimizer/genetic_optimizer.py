"""
Genetic Algorithm (GA) Strategy Parameter Optimization Engine.
Simulates natural selection across populations of parameter genomes to evolve
high-Sharpe, low-drawdown parameter configurations.
"""

from __future__ import annotations
from dataclasses import dataclass, field
import logging
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("autotrade.optimizer.genetic_optimizer")


@dataclass
class Chromosome:
    """Individual genome representing a candidate parameter configuration."""
    genes: Dict[str, Any]
    fitness: float = -999.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0


class GeneticOptimizer:
    """
    Multi-generation Genetic Algorithm optimizer.
    Evolves optimal strategy parameters using elitism, tournament selection, and mutation.
    """
    def __init__(
        self,
        param_bounds: Dict[str, Tuple[Any, Any, str]], # {param_name: (min, max, 'int'|'float')}
        population_size: int = 24,
        generations: int = 8,
        mutation_rate: float = 0.15,
        elite_count: int = 2
    ):
        self.param_bounds = param_bounds
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate
        self.elite_count = elite_count

    def _random_gene_value(self, p_min: Any, p_max: Any, p_type: str) -> Any:
        """Generates random gene value within bounded range."""
        if p_type == "int":
            return random.randint(int(p_min), int(p_max))
        return round(random.uniform(float(p_min), float(p_max)), 4)

    def _create_random_chromosome(self) -> Chromosome:
        """Creates a randomized chromosome from parameter bounds."""
        genes = {}
        for k, (p_min, p_max, p_type) in self.param_bounds.items():
            genes[k] = self._random_gene_value(p_min, p_max, p_type)
        return Chromosome(genes=genes)

    def optimize(
        self,
        fitness_fn: Callable[[Dict[str, Any]], Dict[str, float]]
    ) -> Dict[str, Any]:
        """
        Executes evolutionary optimization loop over specified generations.
        `fitness_fn(genes)` returns dict with {"sharpe", "profit_factor", "drawdown"}.
        """
        population = [self._create_random_chromosome() for _ in range(self.population_size)]
        best_overall = Chromosome(genes={})

        for gen in range(self.generations):
            # 1. Evaluate fitness for all chromosomes
            for chrom in population:
                metrics = fitness_fn(chrom.genes)
                sharpe = metrics.get("sharpe", 0.0)
                pf = metrics.get("profit_factor", 1.0)
                dd = metrics.get("drawdown", 10.0)
                
                # Multi-objective fitness function
                fitness = sharpe * pf * max(0.1, (1.0 - (dd / 100.0)))
                chrom.fitness = fitness
                chrom.sharpe_ratio = sharpe
                chrom.profit_factor = pf
                chrom.max_drawdown = dd

            # Sort population descending by fitness
            population.sort(key=lambda c: c.fitness, reverse=True)
            if population[0].fitness > best_overall.fitness:
                best_overall = Chromosome(
                    genes=dict(population[0].genes),
                    fitness=population[0].fitness,
                    sharpe_ratio=population[0].sharpe_ratio,
                    profit_factor=population[0].profit_factor,
                    max_drawdown=population[0].max_drawdown
                )

            logger.info(
                f"GA Generation {gen + 1}/{self.generations} | Best Fitness: {population[0].fitness:.2f} "
                f"| Sharpe: {population[0].sharpe_ratio:.2f} | PF: {population[0].profit_factor:.2f}"
            )

            # 2. Selection and Reproduction for next generation
            next_generation: List[Chromosome] = []
            
            # Elitism: Retain top performers unchanged
            for e in range(min(self.elite_count, len(population))):
                next_generation.append(Chromosome(genes=dict(population[e].genes)))

            # Fill remaining population via Crossover & Mutation
            while len(next_generation) < self.population_size:
                parent1 = self._tournament_selection(population)
                parent2 = self._tournament_selection(population)
                child = self._crossover(parent1, parent2)
                self._mutate(child)
                next_generation.append(child)

            population = next_generation

        return {
            "best_parameters": best_overall.genes,
            "best_fitness": round(best_overall.fitness, 3),
            "sharpe_ratio": round(best_overall.sharpe_ratio, 2),
            "profit_factor": round(best_overall.profit_factor, 2),
            "max_drawdown": round(best_overall.max_drawdown, 2),
            "generations_completed": self.generations
        }

    def _tournament_selection(self, population: List[Chromosome], k: int = 3) -> Chromosome:
        """Picks the fittest individual from k random candidates."""
        candidates = random.sample(population, min(k, len(population)))
        return max(candidates, key=lambda c: c.fitness)

    def _crossover(self, parent1: Chromosome, parent2: Chromosome) -> Chromosome:
        """Uniform crossover combining genes from both parents."""
        child_genes = {}
        for k in self.param_bounds.keys():
            child_genes[k] = parent1.genes[k] if random.random() < 0.5 else parent2.genes[k]
        return Chromosome(genes=child_genes)

    def _mutate(self, chrom: Chromosome) -> None:
        """Applies random mutation to genes based on mutation rate."""
        for k, (p_min, p_max, p_type) in self.param_bounds.items():
            if random.random() < self.mutation_rate:
                chrom.genes[k] = self._random_gene_value(p_min, p_max, p_type)
