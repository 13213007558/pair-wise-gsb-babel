
    # State for the argument currently being parsed at call depth 1.
    arg_name = None  # keyword parameter name of the current argument
    arg_star = ''  # '*', '**' or '' for unpacking arguments
    arg_lineno = None  # line number where the current argument starts
    arg_started = False  # whether the current argument has any value tokens
    pending_name = None  # a NAME token that may be a keyword parameter name

    def flush_argument():
        nonlocal arg_name, arg_star, arg_lineno, arg_started, pending_name
        messages.append(
            _CallArgument(arg_name, ''.join(buf) if buf else None, arg_lineno or lineno, arg_star),
        )
        del buf[:]
        arg_name = None
        arg_star = ''
        arg_lineno = None
        arg_started = False
        pending_name = None

