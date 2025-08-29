"""
Pricing service for calculating Good-Better-Best HVAC pricing estimates
Implements exact specifications from requirements document
"""
from typing import Dict, Any

class PricingService:
    def __init__(self):
        # Pricing matrix - exact specifications from requirements
        self.pricing_matrix = [
            {
                "tonnage": 2.5,
                "good": {"minPrice": 8500, "maxPrice": 10500},
                "better": {"minPrice": 11000, "maxPrice": 13000},
                "best": {"minPrice": 14000, "maxPrice": 16500}
            },
            {
                "tonnage": 3.5,
                "good": {"minPrice": 9500, "maxPrice": 11500},
                "better": {"minPrice": 13500, "maxPrice": 15500},
                "best": {"minPrice": 17000, "maxPrice": 19500}
            },
            {
                "tonnage": 4.0,
                "good": {"minPrice": 10500, "maxPrice": 12500},
                "better": {"minPrice": 14500, "maxPrice": 16500},
                "best": {"minPrice": 18000, "maxPrice": 21000}
            },
            {
                "tonnage": 5.0,
                "good": {"minPrice": 11500, "maxPrice": 14000},
                "better": {"minPrice": 15500, "maxPrice": 18000},
                "best": {"minPrice": 19500, "maxPrice": 23000}
            }
        ]

    def determine_tonnage(self, square_footage: str) -> float:
      
        if "Under 1,500" in square_footage or "under 1500" in square_footage.lower():
            return 2.5
        elif "1,500 - 2,200" in square_footage or "1500-2200" in square_footage:
            return 3.5
        elif "2,200 - 3,000" in square_footage or "2200-3000" in square_footage:
            return 4.0
        elif "Over 3,000" in square_footage or "over 3000" in square_footage.lower():
            return 5.0
        else:
            # Default fallback
            return 3.5

    def get_pricing_for_tonnage(self, tonnage: float) -> Dict[str, Any]:
        """Find the pricing object for the given tonnage"""
        for pricing_obj in self.pricing_matrix:
            if pricing_obj["tonnage"] == tonnage:
                return pricing_obj
        
        # Fallback to closest tonnage if exact match not found
        closest = min(self.pricing_matrix, key=lambda x: abs(x["tonnage"] - tonnage))
        return closest

    def apply_multi_system_multiplier(self, pricing: Dict[str, Any], system_count: int) -> Dict[str, Any]:
       
        if system_count >= 2:
            multiplier = 1.85
            for tier in ["good", "better", "best"]:
                pricing[tier]["minPrice"] = int(pricing[tier]["minPrice"] * multiplier)
                pricing[tier]["maxPrice"] = int(pricing[tier]["maxPrice"] * multiplier)
        
        return pricing

    def extract_system_count(self, system_count_answer: str) -> int:
        """Extract system count from quiz answer"""
        if not system_count_answer:
            return 1
        
        if "1" in system_count_answer:
            return 1
        elif "2" in system_count_answer:
            return 2
        elif "3" in system_count_answer:
            return 3
        elif "4" in system_count_answer:
            return 4
        else:
            return 1  # Default fallback

    def calculate_estimate(
        self, 
        square_footage: str, 
        system_count: int, 
    ) -> Dict[str, Any]:
     
        
        # Step A: Determine Required Tonnage
        tonnage = self.determine_tonnage(square_footage)
        
        # Step B: Get base pricing from matrix
        base_pricing = self.get_pricing_for_tonnage(tonnage)
        
        # Step C: Apply multiplier for multi-system homes
        final_pricing = self.apply_multi_system_multiplier(base_pricing.copy(), system_count)
        
        # Create the API response in exact format specified
        estimates = {
            "good": {
                "label": "Budget-Focused",
                "minPrice": final_pricing["good"]["minPrice"],
                "maxPrice": final_pricing["good"]["maxPrice"]
            },
            "better": {
                "label": "Efficiency & Value", 
                "minPrice": final_pricing["better"]["minPrice"],
                "maxPrice": final_pricing["better"]["maxPrice"]
            },
            "best": {
                "label": "Ultimate Comfort",
                "minPrice": final_pricing["best"]["minPrice"],
                "maxPrice": final_pricing["best"]["maxPrice"]
            }
        }
        
        return {
            "estimates": estimates,
            "tonnage": tonnage,
            "systemCount": system_count
        }
