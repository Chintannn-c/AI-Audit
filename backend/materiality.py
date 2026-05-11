from typing import Dict, Any

class MaterialityCalculator:
    def __init__(self, npbt: float, romm: str):
        self.npbt = npbt
        self.romm = romm.lower()
        
    def calculate(self, perf_mat_pct: float = 75.0, trivial_pct: float = 3.0, explicit_overall_pct: float = None) -> Dict[str, Any]:
        """
        Calculates materiality based on Suggested Materiality Range or an explicit percentage.
        High RoMM: 5% - 7%
        Medium RoMM: 7% - 8%
        Low RoMM: 8% - 10%
        """
        if explicit_overall_pct is not None:
            overall_pct = explicit_overall_pct
        else:
            # Overall Materiality %
            if self.romm == 'high':
                overall_pct = 6.0 # Mid of 5-7%
            elif self.romm == 'medium':
                overall_pct = 7.5 # Mid of 7-8%
            else: # low
                overall_pct = 9.0 # Mid of 8-10%
            
        overall_materiality = self.npbt * (overall_pct / 100.0)
        
        # Performance Materiality (Suggested 50% to 90%)
        # For High RoMM, usually lower % (e.g. 50-60%)
        # For Low RoMM, usually higher % (e.g. 80-90%)
        performance_materiality = overall_materiality * (perf_mat_pct / 100.0)
        
        # Trivial Threshold (Suggested 0% to 5%)
        trivial_threshold = overall_materiality * (trivial_pct / 100.0)
        
        return {
            "overall_materiality": overall_materiality,
            "overall_pct": overall_pct,
            "performance_materiality": performance_materiality,
            "performance_pct": perf_mat_pct,
            "trivial_threshold": trivial_threshold,
            "trivial_pct": trivial_pct,
            "benchmark": "NPBT"
        }
