import codecs
import re

with codecs.open('prash/cli.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add diagnose_gcp_instance to imports
if 'diagnose_gcp_instance' not in content:
    content = content.replace(
        'diagnose_aws_instance,',
        'diagnose_aws_instance,\n    diagnose_gcp_instance,'
    )
    if 'diagnose_aws_instance' not in content:
        # In case the import was different
        content = content.replace(
            'from .fix import (',
            'from .fix import (\n    diagnose_gcp_instance,'
        )
        if 'diagnose_gcp_instance' not in content:
             content = content.replace(
                'from .fix import ',
                'from .fix import diagnose_gcp_instance, '
            )

# Add run_gcp_watch_loop to imports
if 'run_gcp_watch_loop' not in content:
    content = content.replace(
        'run_aws_watch_loop,',
        'run_aws_watch_loop,\n    run_gcp_watch_loop,'
    )
    if 'run_aws_watch_loop' not in content:
        content = content.replace(
            'from .watcher import ',
            'from .watcher import run_gcp_watch_loop, '
        )

# Update fix routing
fix_aws_block = """    if provider == "aws":
        try:
            diagnosis = asyncio.run(diagnose_aws_instance(args.target, creds))
        except FixTargetError as exc:
            console.print(f"[red]{exc}[/red]")
            return 2
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]AWS instance diagnosis failed: {exc}[/red]")
            return 2
        
        render_diagnosis(diagnosis, console)
        
        action_id = recommended_action_id(diagnosis.recommended_action)
        if action_id is None:
            _render_no_auto_action(diagnosis.recommended_action, args.target)
            return 0

        dispatcher = _build_dispatcher(mode)
        ctx = _make_context(args, store, creds, resource=args.target, env=args.env)
        try:
            result = dispatcher.run(action_id, ctx, ask=None if args.noninteractive else CliAsk())
        except KeyError as exc:
            console.print(f"[red]{exc}[/red]")
            return 2
        except MissingSecretError as exc:
            console.print(f"[yellow]secret '{exc.name}' required: {exc.hint}[/yellow]")
            return 3
        return _render_run_result(result)"""

fix_gcp_block = """
    if provider == "gcp":
        try:
            diagnosis = asyncio.run(diagnose_gcp_instance(args.target, creds))
        except FixTargetError as exc:
            console.print(f"[red]{exc}[/red]")
            return 2
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]GCP instance diagnosis failed: {exc}[/red]")
            return 2
        
        render_diagnosis(diagnosis, console)
        
        action_id = recommended_action_id(diagnosis.recommended_action)
        if action_id is None:
            _render_no_auto_action(diagnosis.recommended_action, args.target)
            return 0

        dispatcher = _build_dispatcher(mode)
        ctx = _make_context(args, store, creds, resource=args.target, env=args.env)
        try:
            result = dispatcher.run(action_id, ctx, ask=None if args.noninteractive else CliAsk())
        except KeyError as exc:
            console.print(f"[red]{exc}[/red]")
            return 2
        except MissingSecretError as exc:
            console.print(f"[yellow]secret '{exc.name}' required: {exc.hint}[/yellow]")
            return 3
        return _render_run_result(result)
"""

if 'if provider == "gcp":' not in content:
    content = content.replace(fix_aws_block, fix_aws_block + fix_gcp_block)


# Update watch routing
watch_aws_block = """    if provider == "aws":
        console.print(f"Starting AWS watcher for target: {args.target}...")
        state = run_aws_watch_loop(args.target, interval, console, max_iterations=max_iters, creds=creds)
        return 0 if state is not None else 1"""

watch_gcp_block = """
    if provider == "gcp":
        console.print(f"Starting GCP watcher for target: {args.target}...")
        state = run_gcp_watch_loop(args.target, interval, console, max_iterations=max_iters, creds=creds)
        return 0 if state is not None else 1
"""

if 'if provider == "gcp":' not in content.split('def cmd_watch(')[-1]:
    content = content.replace(watch_aws_block, watch_aws_block + watch_gcp_block)

with codecs.open('prash/cli.py', 'w', encoding='utf-8') as f:
    f.write(content)
