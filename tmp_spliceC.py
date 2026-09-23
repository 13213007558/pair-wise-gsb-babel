        elif funcname and len(call_stack) == 1:
            nested = tok == NAME and value in keywords
            if (tok == OP and value == ')') or nested:
                flush_argument()

                if any(arg.name is not None or arg.star for arg in messages):
                    # The call used keyword arguments or argument unpacking;
                    # emit the enriched argument representation so that the
                    # arguments can be matched against named keyword
                    # specifications.
                    collected = tuple(messages)
                else:
                    values = [arg.value for arg in messages]
                    collected = tuple(values) if len(values) > 1 else values[0]

                if translator_comments:
                    last_comment_lineno = translator_comments[-1][0]
                    if last_comment_lineno < min(message_lineno, call_stack[-1]) - 1:
                        # Comments don't apply unless they immediately
                        # precede the message, or the line where the parenthesis token
                        # to start this message's translation call is.
                        translator_comments.clear()

                yield (
                    message_lineno,
                    funcname,
                    collected,
                    [comment[1] for comment in translator_comments],
                )

                funcname = lineno = message_lineno = None
                call_stack.clear()
                messages = []
                translator_comments = []
                in_translator_comments = False
                if nested:
                    funcname = value
            elif tok == STRING:
                val = _parse_python_string(value, encoding, future_flags)
                if val is not None:
                    if not message_lineno:
                        message_lineno = lineno
                    buf.append(val)
                arg_started = True
                if arg_lineno is None:
                    arg_lineno = lineno

            # Python 3.12+, see https://peps.python.org/pep-0701/#new-tokens
            elif tok == FSTRING_START:
                current_fstring_start = value
                if not message_lineno:
                    message_lineno = lineno
                arg_started = True
                if arg_lineno is None:
                    arg_lineno = lineno
            elif tok == FSTRING_MIDDLE:
                if current_fstring_start is not None:
                    current_fstring_start += value
            elif tok == FSTRING_END:
                if current_fstring_start is not None:
                    fstring = current_fstring_start + value
                    val = _parse_python_string(fstring, encoding, future_flags)
                    if val is not None:
                        buf.append(val)

            elif tok == OP and value == ',':
                flush_argument()
                if translator_comments:
                    # We have translator comments, and since we're on a
                    # comma(,) user is allowed to break into a new line
                    # Let's increase the last comment's lineno in order
                    # for the comment to still be a valid one
                    old_lineno, old_comment = translator_comments.pop()
                    translator_comments.append((old_lineno + 1, old_comment))

            elif tok == OP and value == '=' and pending_name is not None and not buf:
                # `name=` at call depth: a keyword argument.
                arg_name, arg_lineno = pending_name
                pending_name = None
            elif (
                tok == OP
                and value in ('*', '**')
                and pending_name is None
                and arg_name is None
                and not buf
                and not arg_started
                and not arg_star
            ):
                # `*args` or `**kwargs` unpacking.
                arg_star = value
                if arg_lineno is None:
                    arg_lineno = lineno
                if not message_lineno:
                    message_lineno = lineno
            elif tok == NAME and arg_name is None and not buf and not arg_started and not arg_star:
                # A bare name may turn out to be a keyword argument name
                # if an `=` token follows.
                pending_name = (value, lineno)
                if arg_lineno is None:
                    arg_lineno = lineno
                if not message_lineno:
                    message_lineno = lineno
            elif tok == COMMENT:
                if not message_lineno:
                    message_lineno = lineno
            elif tok != NL:
                # Any other token is part of a runtime expression.
                pending_name = None
                arg_started = True
                if arg_lineno is None:
                    arg_lineno = lineno
                if not message_lineno:
                    message_lineno = lineno

