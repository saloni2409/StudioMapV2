import sys
import os
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from ai import pdf_to_profiles
from models import StudioProfile

def test_pdf_to_profiles_multi():
    print("Testing pdf_to_profiles with multiple studios...")
    
    mock_data = {
        "studios": [
            {
                "name": "Studio A",
                "tagline": "Tagline A",
                "description": "Desc A",
                "affordances": {"individual_work": True},
                "tools": [{"name": "Tool A1", "quantity": 5}],
                "coursework": [{"topic": "Topic A1", "teaching_plan": "Plan A1"}]
            },
            {
                "name": "Studio B",
                "tagline": "Tagline B",
                "description": "Desc B",
                "affordances": {"pair_work": True},
                "tools": [{"name": "Tool B1", "quantity": 2}],
                "coursework": [{"topic": "Topic B1", "teaching_plan": "Plan B1"}]
            }
        ]
    }
    
    mock_provider = MagicMock()
    mock_provider.extract_json_from_pdf.return_value = mock_data
    
    with patch("ai.get_provider", return_value=mock_provider):
        profiles = pdf_to_profiles(b"dummy pdf bytes")
        
        assert len(profiles) == 2
        assert profiles[0].name == "Studio A"
        assert profiles[0].affordances.individual_work is True
        assert len(profiles[0].tools) == 1
        assert profiles[0].tools[0].name == "Tool A1"
        
        assert profiles[1].name == "Studio B"
        assert profiles[1].affordances.pair_work is True
        assert len(profiles[1].tools) == 1
        assert profiles[1].tools[0].name == "Tool B1"
        
    print("✅ pdf_to_profiles_multi passed!")

def test_pdf_to_profiles_single_legacy():
    print("Testing pdf_to_profiles with single studio (legacy format)...")
    
    mock_data = {
        "name": "Single Studio",
        "tagline": "Single Tagline",
        "description": "Single Desc",
        "affordances": {"group_work": True},
        "tools": [{"name": "Single Tool", "quantity": 1}],
        "coursework": []
    }
    
    mock_provider = MagicMock()
    mock_provider.extract_json_from_pdf.return_value = mock_data
    
    with patch("ai.get_provider", return_value=mock_provider):
        profiles = pdf_to_profiles(b"dummy pdf bytes")
        
        assert len(profiles) == 1
        assert profiles[0].name == "Single Studio"
        assert profiles[0].affordances.group_work is True
        
    print("✅ pdf_to_profiles_single_legacy passed!")

if __name__ == "__main__":
    try:
        test_pdf_to_profiles_multi()
        test_pdf_to_profiles_single_legacy()
        print("\nAll tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
