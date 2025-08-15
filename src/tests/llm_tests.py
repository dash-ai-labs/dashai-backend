import json


def test_llm_classifications(classifier_fn, data_path="src/tests/email_class_data.json"):
    """
    classifier_fn: function(email_text) -> list of predicted categories (strings)
    data_path: path to your labeled JSON data file
    
    Prints accuracy and mismatches.
    
    example usage:
        from src.tests.llm_tests import test_llm_classifications
        from src.libs.llm_utils import classify emails
    
        test_llm_classifications(classify_email)
    """
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    total = len(data)
    correct = 0
    mismatches = []
    
    for i, entry in enumerate(data):
        text = entry["text"]
        true_classes = entry.get("categories", [])
        
        pred_classes, _ = classifier_fn(text)
        
        if pred_classes == true_classes:
            correct += 1
        else:
            mismatches.append({
                "index": i,
                "true": true_classes,
                "predicted": pred_classes,
                "text_snippet": text[:200].replace("\n", " ") + "..."
            })
    
    accuracy = correct / total if total > 0 else 0
    print(f"Total samples: {total}")
    print(f"Correct classifications: {correct}")
    print(f"Accuracy: {accuracy:.2%}")
    
    if mismatches:
        print(f"\nMismatches ({len(mismatches)}):")
        for m in mismatches:
            print(f"- Index {m['index']}: True={m['true']}, Predicted={m['predicted']}")
            print(f"  Text snippet: {m['text_snippet']}")
            print()