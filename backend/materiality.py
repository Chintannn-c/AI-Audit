from typing import Dict, Any

class MaterialityCalculator:
    def __init__(self, value: float, benchmark: str, romm: str):
        self.value = value
        self.benchmark = benchmark.upper() # NPBT, REVENUE, ASSETS
        self.romm = romm.lower()
        
    def calculate(self, perf_mat_pct: float = 75.0, trivial_pct: float = 3.0, explicit_overall_pct: float = None) -> Dict[str, Any]:
        """
        Calculates materiality based on Benchmark-specific ranges or explicit percentage.
        
        Ranges (Industry Standard):
        - NPBT: 5% - 10%
        - REVENUE: 0.5% - 1.0%
        - ASSETS: 1.0% - 2.0%
        """
        if explicit_overall_pct is not None:
            overall_pct = explicit_overall_pct
        else:
            # Determine Overall Materiality % based on Benchmark and RoMM
            if self.benchmark == 'NPBT':
                ranges = (5.0, 10.0)
            elif self.benchmark == 'REVENUE':
                ranges = (0.5, 1.0)
            elif self.benchmark == 'ASSETS':
                ranges = (1.0, 2.0)
            else:
                ranges = (1.0, 5.0) # Fallback

            # RoMM adjustment within range
            if self.romm == 'high':
                overall_pct = ranges[0] + (ranges[1] - ranges[0]) * 0.2 # Lower end
            elif self.romm == 'medium':
                overall_pct = ranges[0] + (ranges[1] - ranges[0]) * 0.5 # Middle
            else: # low
                overall_pct = ranges[0] + (ranges[1] - ranges[0]) * 0.8 # Higher end
            
        overall_materiality = self.value * (overall_pct / 100.0)
        
        # Performance Materiality (Percentage of Overall Materiality)
        performance_materiality = overall_materiality * (perf_mat_pct / 100.0)
        
        # Trivial Threshold (Percentage of Overall Materiality)
        trivial_threshold = overall_materiality * (trivial_pct / 100.0)
        
        return {
            "overall_materiality": overall_materiality,
            "overall_pct": round(overall_pct, 2),
            "performance_materiality": performance_materiality,
            "performance_pct": perf_mat_pct,
            "trivial_threshold": trivial_threshold,
            "trivial_pct": trivial_pct,
            "benchmark": self.benchmark,
            "base_value": self.value
        }
