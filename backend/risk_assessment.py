from typing import List, Dict, Any

class RiskAssessmentEngine:
    def __init__(self, turnover_above_250: bool, ifc_applicable: bool, weak_governance: bool, prev_misstatements: bool):
        self.turnover_above_250 = turnover_above_250
        self.ifc_applicable = ifc_applicable
        self.weak_governance = weak_governance
        self.prev_misstatements = prev_misstatements

    def assess(self) -> Dict[str, Any]:
        """
        Determine if this is a LARGE AUDIT requiring a combined approach (TOD + TOC),
        based on turnover or qualitative risk factors.
        """
        is_large_audit = (
            self.turnover_above_250 or 
            self.ifc_applicable or 
            self.weak_governance or 
            self.prev_misstatements
        )
        
        # Risk Scoring
        risk_score = 0
        if self.weak_governance: risk_score += 40
        if self.prev_misstatements: risk_score += 40
        if is_large_audit: risk_score += 20
        
        classification = "High" if risk_score >= 60 else ("Medium" if risk_score >= 30 else "Low")
        
        return {
            "audit_type": "LARGE AUDIT" if is_large_audit else "NORMAL AUDIT",
            "risk_score": risk_score,
            "classification": classification,
            "control_reliance": "Low" if risk_score > 50 else ("Medium" if risk_score > 30 else "High"),
            "control_reliance_score": 100 - risk_score,
            "suggested_approach": "Substantive Testing" if risk_score > 50 else "Combined Approach (Control + Substantive)"
        }
