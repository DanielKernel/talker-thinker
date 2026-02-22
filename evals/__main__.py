"""
评测系统 CLI 入口

使用方式:
    python -m evals run                     # 运行全部评测
    python -m evals run --category simple   # 运行特定类别
    python -m evals report --format html    # 生成报告
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

from .harness import EvalRunner, EvalConfig
from .cases import get_all_cases, get_cases_by_category
from .core.types import EvalCategory, Priority
from .reporters.console import ConsoleReporter
from .reporters.json_reporter import JSONReporter
from .reporters.html import HTMLReporter


def cmd_run(args):
    """运行评测"""
    print("🚀 开始运行评测...")

    # 构建配置
    config = EvalConfig(
        use_mock_llm=not args.real_llm,
        show_progress=args.verbose,
        category_filter=None,
    )

    if args.category:
        try:
            config.category_filter = EvalCategory(args.category)
        except ValueError:
            print(f"❌ 无效的类别：{args.category}")
            print("有效类别：simple, medium, complex, edge")
            sys.exit(1)

    if args.timeout:
        config.case_timeout_seconds = args.timeout

    if args.latency:
        config.mock_talker_latency_ms = args.latency

    # 创建 Runner 并运行
    runner = EvalRunner(config)

    try:
        eval_result = asyncio.run(runner.run())
    except KeyboardInterrupt:
        print("\n⚠️  评测被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 评测执行失败：{e}")
        sys.exit(1)

    # 输出结果
    if args.verbose:
        reporter = ConsoleReporter(verbose=True)
        reporter.print(eval_result)
    else:
        # 简洁输出
        print(f"\n📊 评测完成")
        print(f"   总用例：{eval_result.total_cases}")
        print(f"   通过：{eval_result.passed_cases} ({eval_result.pass_rate:.1f}%)")
        print(f"   失败：{eval_result.failed_cases}")
        print(f"   平均得分：{eval_result.average_score:.1f}")
        print(f"   平均响应时间：{eval_result.average_response_time:.1f}ms")

    # 导出结果
    if args.output:
        # JSON 导出
        json_reporter = JSONReporter()
        json_path = json_reporter.export(eval_result, args.output)
        print(f"\n💾 结果已保存到：{json_path}")

    if args.html:
        html_reporter = HTMLReporter()
        html_path = args.html
        if not html_path.endswith(".html"):
            html_path = html_path + ".html"
        html_reporter.export(eval_result, html_path)
        print(f"📄 HTML 报告已生成：{html_path}")

    # 返回退出码
    sys.exit(0 if eval_result.pass_rate >= 85 else 1)


def cmd_list(args):
    """列出评测用例"""
    if args.category:
        try:
            category = EvalCategory(args.category)
            cases = get_cases_by_category(category)
        except ValueError:
            print(f"❌ 无效的类别：{args.category}")
            print("有效类别：simple, medium, complex, edge")
            sys.exit(1)
    else:
        cases = get_all_cases()

    print(f"📋 评测用例列表 (共 {len(cases)} 个)\n")

    current_category = None
    for case in cases:
        if case.category != current_category:
            current_category = case.category
            print(f"\n{'='*60}")
            print(f"【{category_name(current_category)}】")
            print(f"{'='*60}")

        priority_mark = {
            Priority.CRITICAL: "🔴",
            Priority.HIGH: "🟡",
            Priority.NORMAL: "🟢",
            Priority.LOW: "⚪",
        }.get(case.priority, "")

        print(f"  {priority_mark} {case.case_id}: {case.name}")
        print(f"      {case.description}")
        print(f"      期望 Agent: {case.expected_agent.value}")
        print(f"      期望复杂度：{case.expected_complexity.value}")
        if case.assertions:
            print(f"      断言数：{len(case.assertions)}")
        print()


def cmd_report(args):
    """生成报告"""
    # 读取之前的评测结果
    if not args.input:
        print("❌ 请指定输入文件：--input <result.json>")
        sys.exit(1)

    import json

    try:
        with open(args.input, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ 文件不存在：{args.input}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败：{e}")
        sys.exit(1)

    # 从字典重建 EvalResult
    from .core.types import EvalResult, CaseResult, AssertionResult, FailureReason, AgentRole, TaskComplexity

    case_results = []
    for cr in data.get("case_results", []):
        assertion_results = [
            AssertionResult(
                assertion_name=ar["assertion_name"],
                passed=ar["passed"],
                weight=ar["weight"],
                failure_reason=ar.get("failure_reason", ""),
            )
            for ar in cr.get("assertion_results", [])
        ]

        failure_reason = None
        if cr.get("failure_reason"):
            try:
                failure_reason = FailureReason(cr["failure_reason"])
            except ValueError:
                pass

        case_results.append(CaseResult(
            case_id=cr["case_id"],
            case_name=cr["case_name"],
            passed=cr["passed"],
            actual_agent=AgentRole(cr["actual_agent"]),
            actual_complexity=TaskComplexity(cr["actual_complexity"]),
            actual_output=cr["actual_output"],
            response_time_ms=cr["response_time_ms"],
            assertion_results=assertion_results,
            failure_reason=failure_reason,
            failure_details=cr.get("failure_details", ""),
            tokens_used=cr.get("tokens_used", 0),
            timestamp=cr.get("timestamp", 0),
        ))

    eval_result = EvalResult(
        run_id=data.get("run_id", ""),
        case_results=case_results,
        start_time=data.get("start_time", 0),
        end_time=data.get("end_time", 0),
        total_cases=data.get("total_cases", 0),
        passed_cases=data.get("passed_cases", 0),
        failed_cases=data.get("failed_cases", 0),
    )

    # 生成报告
    fmt = args.format.lower()

    if fmt == "json":
        reporter = JSONReporter()
        output = args.output or "eval_report.json"
        reporter.export(eval_result, output)
        print(f"✅ JSON 报告已生成：{output}")

    elif fmt == "html":
        reporter = HTMLReporter()
        output = args.output or "eval_report.html"
        if not output.endswith(".html"):
            output += ".html"
        reporter.export(eval_result, output)
        print(f"✅ HTML 报告已生成：{output}")

    elif fmt == "console":
        reporter = ConsoleReporter(verbose=True)
        reporter.print(eval_result)

    else:
        print(f"❌ 不支持的报告格式：{fmt}")
        print("支持格式：json, html, console")
        sys.exit(1)


def category_name(category: EvalCategory) -> str:
    """获取类别中文名"""
    names = {
        EvalCategory.SIMPLE: "简单任务",
        EvalCategory.MEDIUM: "中等任务",
        EvalCategory.COMPLEX: "复杂任务",
        EvalCategory.EDGE: "边界/异常",
    }
    return names.get(category, str(category))


def main():
    parser = argparse.ArgumentParser(
        description="Talker-Thinker 评测系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m evals run                          # 运行全部评测
  python -m evals run --category simple        # 运行简单任务评测
  python -m evals run --verbose --output result.json
  python -m evals list                         # 列出所有评测用例
  python -m evals list --category complex
  python -m evals report --input result.json --format html
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # run 命令
    run_parser = subparsers.add_parser("run", help="运行评测")
    run_parser.add_argument(
        "--category", "-c",
        choices=["simple", "medium", "complex", "edge"],
        help="运行特定类别的评测",
    )
    run_parser.add_argument(
        "--output", "-o",
        help="输出结果文件路径 (JSON 格式)",
    )
    run_parser.add_argument(
        "--html", "-H",
        nargs="?",
        const="eval_report.html",
        help="生成 HTML 报告 (可选指定文件名)",
    )
    run_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="显示详细输出",
    )
    run_parser.add_argument(
        "--real-llm",
        action="store_true",
        help="使用真实 LLM (默认使用 Mock)",
    )
    run_parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="用例超时时间 (秒)",
    )
    run_parser.add_argument(
        "--latency",
        type=float,
        help="Mock 响应延迟 (ms)",
    )
    run_parser.set_defaults(func=cmd_run)

    # list 命令
    list_parser = subparsers.add_parser("list", help="列出评测用例")
    list_parser.add_argument(
        "--category", "-c",
        choices=["simple", "medium", "complex", "edge"],
        help="列出特定类别的评测用例",
    )
    list_parser.set_defaults(func=cmd_list)

    # report 命令
    report_parser = subparsers.add_parser("report", help="生成报告")
    report_parser.add_argument(
        "--input", "-i",
        required=True,
        help="输入文件路径 (JSON 格式)",
    )
    report_parser.add_argument(
        "--output", "-o",
        help="输出文件路径",
    )
    report_parser.add_argument(
        "--format", "-f",
        choices=["json", "html", "console"],
        default="console",
        help="报告格式 (默认：console)",
    )
    report_parser.set_defaults(func=cmd_report)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
