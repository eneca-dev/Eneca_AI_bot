"""Manual test script for Analytics Agent"""
import requests
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

BASE_URL = "http://localhost:8000"

def test_analytics_endpoint(query: str, user_role: str = "admin"):
    """Test analytics endpoint with a query"""
    console.print(f"\n[bold blue]Testing query:[/bold blue] {query}")
    console.print(f"[dim]Role: {user_role}[/dim]")

    try:
        response = requests.post(
            f"{BASE_URL}/api/analytics",
            json={
                "query": query,
                "user_role": user_role
            },
            timeout=30
        )

        console.print(f"[green]Status: {response.status_code}[/green]")

        if response.status_code == 200:
            data = response.json()

            # Display response structure
            console.print("\n[bold cyan]Response Structure:[/bold cyan]")
            console.print(f"  Type: {data.get('type', 'N/A')}")
            console.print(f"  Success: {data.get('success', False)}")

            # Display content
            if data.get('content'):
                console.print("\n[bold cyan]Content:[/bold cyan]")
                console.print(Panel(data['content'], expand=False))

            # Display SQL query
            if data.get('sql_query'):
                console.print("\n[bold cyan]Generated SQL:[/bold cyan]")
                sql_syntax = Syntax(data['sql_query'], "sql", theme="monokai", line_numbers=False)
                console.print(sql_syntax)

            # Display chart config
            if data.get('chart_config'):
                console.print("\n[bold cyan]Chart Config:[/bold cyan]")
                chart_json = json.dumps(data['chart_config'], indent=2, ensure_ascii=False)
                console.print(Syntax(chart_json, "json", theme="monokai", line_numbers=False))

            # Display metadata
            if data.get('metadata'):
                console.print("\n[bold cyan]Metadata:[/bold cyan]")
                for key, value in data['metadata'].items():
                    console.print(f"  {key}: {value}")

            return True
        else:
            console.print(f"[red]Error: {response.text}[/red]")
            return False

    except requests.exceptions.ConnectionError:
        console.print("[red]❌ Connection Error: Is the server running? (python server.py)[/red]")
        return False
    except Exception as e:
        console.print(f"[red]❌ Error: {str(e)}[/red]")
        return False


def main():
    """Run all test cases"""
    console.print("[bold green]Analytics Agent Test Suite[/bold green]\n")
    console.print(f"Testing endpoint: {BASE_URL}/api/analytics\n")

    test_cases = [
        {
            "name": "Test 1: Simple statistics query",
            "query": "Покажи статистику проектов",
            "role": "admin"
        },
        {
            "name": "Test 2: Chart request",
            "query": "Создай круговую диаграмму по статусам проектов",
            "role": "admin"
        },
        {
            "name": "Test 3: Filtered query",
            "query": "Покажи активные проекты",
            "role": "manager"
        },
        {
            "name": "Test 4: Report request",
            "query": "Сформируй отчет по прогрессу проектов",
            "role": "admin"
        },
        {
            "name": "Test 5: SQL generation",
            "query": "Напиши SQL запрос для получения всех проектов с их этапами",
            "role": "admin"
        }
    ]

    results = []

    for i, test_case in enumerate(test_cases, 1):
        console.print(f"\n{'='*80}")
        console.print(f"[bold yellow]{test_case['name']}[/bold yellow]")
        console.print(f"{'='*80}")

        success = test_analytics_endpoint(
            query=test_case['query'],
            user_role=test_case['role']
        )

        results.append({
            "test": test_case['name'],
            "success": success
        })

        # Pause between tests
        if i < len(test_cases):
            console.print("\n[dim]Press Enter to continue to next test...[/dim]")
            input()

    # Summary
    console.print(f"\n{'='*80}")
    console.print("[bold green]Test Summary[/bold green]")
    console.print(f"{'='*80}\n")

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Test", style="cyan")
    table.add_column("Result", justify="center")

    passed = 0
    for result in results:
        status = "✅ PASS" if result['success'] else "❌ FAIL"
        table.add_row(result['test'], status)
        if result['success']:
            passed += 1

    console.print(table)
    console.print(f"\n[bold]Total: {passed}/{len(results)} tests passed[/bold]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Tests interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {str(e)}[/red]")
