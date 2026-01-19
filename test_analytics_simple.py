"""Simple test script for Analytics Agent (no external dependencies except requests)"""
import requests
import json

BASE_URL = "http://localhost:8000"


def test_analytics(query: str, user_role: str = "admin"):
    """Test analytics endpoint"""
    print(f"\n{'='*80}")
    print(f"Query: {query}")
    print(f"Role: {user_role}")
    print(f"{'='*80}")

    try:
        response = requests.post(
            f"{BASE_URL}/api/analytics",
            json={"query": query, "user_role": user_role},
            timeout=30
        )

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            print(f"\n[OK] SUCCESS")
            print(f"\nType: {data.get('type')}")
            print(f"Success: {data.get('success')}")

            if data.get('content'):
                print(f"\n[Content]:")
                print(data['content'])

            if data.get('sql_query'):
                print(f"\n[SQL Query]:")
                print(data['sql_query'])

            if data.get('chart_config'):
                print(f"\n[Chart Config]:")
                print(json.dumps(data['chart_config'], indent=2, ensure_ascii=False))

            if data.get('metadata'):
                print(f"\n[Metadata]:")
                for key, value in data['metadata'].items():
                    print(f"  {key}: {value}")

            return True
        else:
            print(f"\n[FAIL] Request failed")
            print(f"Error: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Connection Error!")
        print("Is the server running? Start it with: python server.py")
        return False
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        return False


def main():
    """Run test cases"""
    print("="*80)
    print("Analytics Agent Test Suite")
    print(f"Endpoint: {BASE_URL}/api/analytics")
    print("="*80)

    tests = [
        ("Покажи статистику проектов", "admin"),
        ("Создай круговую диаграмму по статусам проектов", "admin"),
        ("Покажи активные проекты", "manager"),
        ("Сформируй отчет по прогрессу проектов", "admin"),
    ]

    results = []
    for i, (query, role) in enumerate(tests, 1):
        print(f"\n\nTest {i}/{len(tests)}")
        success = test_analytics(query, role)
        results.append(success)

        if i < len(tests):
            input("\nPress Enter for next test...")

    # Summary
    print("\n\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    passed = sum(results)
    print(f"\nPassed: {passed}/{len(tests)}")
    print(f"Failed: {len(tests) - passed}/{len(tests)}")

    if passed == len(tests):
        print("\n[OK] All tests passed!")
    else:
        print(f"\n[WARNING] {len(tests) - passed} test(s) failed")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {str(e)}")
