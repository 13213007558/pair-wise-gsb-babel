            if funcname:
                call_stack.append(lineno)
                if len(call_stack) > 1 and pending_name is not None:
                    # A name followed by `(` is a call, not a keyword argument.
                    pending_name = None
                    arg_started = True

