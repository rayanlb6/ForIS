"""
EvoPath-GA: Evolutionary Path Optimization using Genetic Algorithm
Implementation of Algorithm 3.2 from thesis
"""
import numpy as np
import random
from typing import List, Tuple, Set
from pathlib import Path
import sys
from deap import base, creator, tools, algorithms

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'kimvieware-shared' / 'src'))
from kimvieware_shared.models import Trajectory

class EvoPathGA:
    """
    Evolutionary Path Optimization using Genetic Algorithm
    
    Multi-objective fitness function (Equation 3.3):
    F(C) = w1·cov(C) + w2·(1 - cost(C)/maxCost) + w3·(1 - |C|/|T|)
    
    Where:
    - cov(C): Coverage ratio
    - cost(C): Total execution cost
    - |C|: Test suite size
    """
    
    def __init__(
        self,
        w1: float = 0.5,  # Coverage weight
        w2: float = 0.3,  # Cost weight  
        w3: float = 0.2,  # Size weight
        population_size: int = 50,
        generations: int = 100,
        crossover_prob: float = 0.7,
        mutation_prob: float = 0.2
    ):
        self.w1 = w1
        self.w2 = w2
        self.w3 = w3
        self.pop_size = population_size
        self.generations = generations
        self.cx_prob = crossover_prob
        self.mut_prob = mutation_prob
    
    def optimize(self, trajectories: List[Trajectory]) -> Tuple[List[Trajectory], dict]:
        """
        Optimize test suite using Genetic Algorithm
        
        Args:
            trajectories: Input trajectory set (from SGATS)
            
        Returns:
            (optimized_set, statistics)
        """
        
        print(f"\n{'='*60}")
        print(f"🧬 EvoPath-GA: Genetic Algorithm Optimization")
        print(f"{'='*60}")
        print(f"Input: {len(trajectories)} trajectories (from SGATS)")
        print(f"Parameters:")
        print(f"   Population: {self.pop_size}")
        print(f"   Generations: {self.generations}")
        print(f"   Crossover: {self.cx_prob}")
        print(f"   Mutation: {self.mut_prob}")
        
        # Setup
        self.trajectories = trajectories
        self.n = len(trajectories)
        self.all_branches = self._get_all_branches(trajectories)
        self.max_cost = sum(t.cost for t in trajectories)
        
        print(f"\n   Total branches: {len(self.all_branches)}")
        print(f"   Max cost: {self.max_cost:.3f}")
        
        # DEAP setup
        self._setup_deap()
        
        # Initialize population
        population = self.toolbox.population(n=self.pop_size)
        
        # Evaluate initial population
        fitnesses = list(map(self.toolbox.evaluate, population))
        for ind, fit in zip(population, fitnesses):
            ind.fitness.values = fit
        
        print(f"\n🔬 Evolution:")
        
        # Track best
        best_fitness_history = []
        
        # Evolve
        for gen in range(self.generations):
            # Select
            offspring = self.toolbox.select(population, len(population))
            offspring = list(map(self.toolbox.clone, offspring))
            
            # Crossover
            for child1, child2 in zip(offspring[::2], offspring[1::2]):
                if random.random() < self.cx_prob:
                    self.toolbox.mate(child1, child2)
                    del child1.fitness.values
                    del child2.fitness.values
            
            # Mutation
            for mutant in offspring:
                if random.random() < self.mut_prob:
                    self.toolbox.mutate(mutant)
                    del mutant.fitness.values
            
            # Evaluate
            invalid_ind = [ind for ind in offspring if not ind.fitness.valid]
            fitnesses = map(self.toolbox.evaluate, invalid_ind)
            for ind, fit in zip(invalid_ind, fitnesses):
                ind.fitness.values = fit
            
            # Replace
            population[:] = offspring
            
            # Track best
            fits = [ind.fitness.values[0] for ind in population]
            best_fit = max(fits)
            best_fitness_history.append(best_fit)
            
            if gen % 20 == 0:
                print(f"   Gen {gen:3d}: Best fitness = {best_fit:.4f}")
        
        # Get best solution
        best_ind = tools.selBest(population, 1)[0]
        optimized_indices = [i for i, bit in enumerate(best_ind) if bit == 1]
        optimized_set = [trajectories[i] for i in optimized_indices]
        
        # Statistics
        stats = self._compute_stats(trajectories, optimized_set, best_fitness_history)
        
        print(f"\n✅ EvoPath-GA Results:")
        print(f"   |T| = {len(trajectories)} → |C| = {len(optimized_set)}")
        print(f"   Size reduction: {stats['size_reduction']*100:.1f}%")
        print(f"   Cost reduction: {stats['cost_reduction']*100:.1f}%")
        print(f"   Coverage: {stats['coverage_rate']*100:.1f}%")
        print(f"   Best fitness: {stats['best_fitness']:.4f}")
        print(f"{'='*60}\n")
        
        return optimized_set, stats
    
    def _setup_deap(self):
        """Setup DEAP genetic algorithm"""
        
        # Create types
        creator.create("FitnessMax", base.Fitness, weights=(1.0,))
        creator.create("Individual", list, fitness=creator.FitnessMax)
        
        # Toolbox
        self.toolbox = base.Toolbox()
        self.toolbox.register("attr_bool", random.randint, 0, 1)
        self.toolbox.register("individual", tools.initRepeat, creator.Individual,
                             self.toolbox.attr_bool, n=self.n)
        self.toolbox.register("population", tools.initRepeat, list, self.toolbox.individual)
        
        # Operators
        self.toolbox.register("evaluate", self._fitness)
        self.toolbox.register("mate", tools.cxTwoPoint)
        self.toolbox.register("mutate", tools.mutFlipBit, indpb=0.1)
        self.toolbox.register("select", tools.selTournament, tournsize=3)
    
    def _fitness(self, individual: List[int]) -> Tuple[float]:
        """
        Multi-objective fitness function (Equation 3.3)
        
        F(C) = w1·cov(C) + w2·(1 - cost(C)/maxCost) + w3·(1 - |C|/|T|)
        """
        
        # Get selected trajectories
        selected_indices = [i for i, bit in enumerate(individual) if bit == 1]
        
        if len(selected_indices) == 0:
            return (0.0,)
        
        selected = [self.trajectories[i] for i in selected_indices]
        
        # Coverage
        covered = self._get_all_branches(selected)
        cov = len(covered) / len(self.all_branches) if self.all_branches else 0
        
        # Cost
        total_cost = sum(t.cost for t in selected)
        cost_norm = 1 - (total_cost / self.max_cost) if self.max_cost > 0 else 1
        
        # Size
        size_norm = 1 - (len(selected) / self.n)
        
        # Combined fitness (Eq 3.3)
        fitness = self.w1 * cov + self.w2 * cost_norm + self.w3 * size_norm
        
        return (fitness,)
    
    def _get_all_branches(self, trajectories: List[Trajectory]) -> Set:
        """Get union of all branches"""
        branches = set()
        for t in trajectories:
            branches.update(t.branches_covered)
        return branches
    
    def _compute_stats(self, original: List[Trajectory], optimized: List[Trajectory],
                       fitness_history: List[float]) -> dict:
        """Compute optimization statistics"""
        
        original_branches = self._get_all_branches(original)
        optimized_branches = self._get_all_branches(optimized)
        
        return {
            'original_count': len(original),
            'optimized_count': len(optimized),
            'size_reduction': 1 - (len(optimized) / len(original)),
            'original_cost': sum(t.cost for t in original),
            'optimized_cost': sum(t.cost for t in optimized),
            'cost_reduction': 1 - (sum(t.cost for t in optimized) / sum(t.cost for t in original)),
            'total_branches': len(original_branches),
            'covered_branches': len(optimized_branches),
            'coverage_rate': len(optimized_branches) / len(original_branches) if original_branches else 1.0,
            'best_fitness': max(fitness_history),
            'generations': len(fitness_history),
            'convergence_history': fitness_history
        }
