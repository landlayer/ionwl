// SPDX-License-Identifier: MIT

use super::*;

#[derive(Default)]
struct Dest {
    path: Option<OsString>,
    verbose: bool,
    rest: Vec<OsString>,
}

fn args_from(args: &[&str]) -> Vec<OsString> {
    args.iter().map(OsString::from).collect()
}

/// Parse, reducing the outcome to the error message.
fn parse_message<T>(
    parser: &mut ArgumentParser<T>,
    dest: &mut T,
    args: &[OsString],
) -> Result<(), String> {
    parser.parse(dest, args).map(|_| ()).map_err(|e| e.message)
}

fn parser_new() -> ArgumentParser<Dest> {
    let mut parser = ArgumentParser::new("test");
    parser.descr_set("Test things.").epilog_set("Epilog.");
    parser.argument_add(Argument {
        metavar: "<PATH>",
        ..Argument::flag(
            "-p",
            "--path",
            "Set the path",
            Params::Count(1),
            |dest: &mut Dest, values| {
                dest.path = Some(values[0].clone());
                Ok(Step::Continue(1))
            },
        )
    });
    let group = parser.group_add("Extra", "Rarely used.");
    parser.argument_add(Argument {
        group: Some(group),
        ..Argument::flag(
            "",
            "--verbose",
            "Print more",
            Params::Count(0),
            |dest: &mut Dest, _| {
                dest.verbose = true;
                Ok(Step::Continue(0))
            },
        )
    });
    parser.argument_add(Argument {
        metavar: "...",
        group: Some(group),
        ..Argument::flag(
            "",
            "--",
            "Pass the remaining arguments",
            Params::Rest,
            |dest: &mut Dest, values| {
                dest.rest = values.to_vec();
                Ok(Step::Continue(values.len()))
            },
        )
    });
    parser
}

// -- Parsing -----------------------------------------------------------------

#[test]
fn parse_short_and_long_flags() {
    let mut parser = parser_new();
    let mut dest = Dest::default();
    parse_message(
        &mut parser,
        &mut dest,
        &args_from(&["--verbose", "-p", "a"]),
    )
    .unwrap();
    assert_eq!(dest.path.as_deref(), Some(OsStr::new("a")));
    assert!(dest.verbose);
}

#[test]
fn parse_rest_takes_every_remaining_argument() {
    let mut parser = parser_new();
    let mut dest = Dest::default();
    parse_message(&mut parser, &mut dest, &args_from(&["--", "-p", "x"])).unwrap();
    assert_eq!(dest.path, None);
    assert_eq!(dest.rest, ["-p", "x"]);
}

#[test]
fn parse_unknown_argument_fails() {
    let mut parser = parser_new();
    let mut dest = Dest::default();
    assert_eq!(
        parse_message(&mut parser, &mut dest, &args_from(&["--bogus"])),
        Err("unknown argument '--bogus'".to_string())
    );
}

#[test]
fn parse_missing_value_fails_without_panicking() {
    let mut parser = parser_new();
    let mut dest = Dest::default();
    assert_eq!(
        parse_message(&mut parser, &mut dest, &args_from(&["--path"])),
        Err("'--path' requires 1 value, 0 given".to_string())
    );
}

#[test]
fn parse_value_that_looks_like_a_flag_is_taken() {
    let mut parser = parser_new();
    let mut dest = Dest::default();
    assert_eq!(
        parse_message(&mut parser, &mut dest, &args_from(&["--path", "--verbose"])),
        Ok(())
    );
    assert_eq!(dest.path.as_deref(), Some(OsStr::new("--verbose")));
    assert!(!dest.verbose);
    assert_eq!(
        parse_message(&mut parser, &mut dest, &args_from(&["-p", "-foo"])),
        Ok(())
    );
    assert_eq!(dest.path.as_deref(), Some(OsStr::new("-foo")));
    assert_eq!(
        parse_message(&mut parser, &mut dest, &args_from(&["--path", "-1"])),
        Ok(())
    );
    assert_eq!(dest.path.as_deref(), Some(OsStr::new("-1")));
}

#[test]
fn parse_callback_error_names_the_flag() {
    let mut parser: ArgumentParser<()> = ArgumentParser::new("prog");
    parser.argument_add(Argument {
        metavar: "<N>",
        ..Argument::flag("-n", "", "", Params::Count(1), |(), values| {
            value_to_str(&values[0])?
                .parse::<u32>()
                .map_err(|e| e.to_string())?;
            Ok(Step::Continue(1))
        })
    });
    assert_eq!(
        parse_message(&mut parser, &mut (), &args_from(&["-n", "x"])),
        Err("'-n': invalid digit found in string".to_string())
    );
}

#[test]
fn parse_required_argument_missing_fails() {
    let mut parser: ArgumentParser<()> = ArgumentParser::new("prog");
    parser.argument_add(Argument {
        required: true,
        ..Argument::flag("-i", "--input", "", Params::Count(0), |(), _| {
            Ok(Step::Continue(0))
        })
    });
    assert_eq!(
        parse_message(&mut parser, &mut (), &[]),
        Err("'-i/--input' is required".to_string())
    );
    assert_eq!(
        parse_message(&mut parser, &mut (), &args_from(&["--input"])),
        Ok(())
    );
}

// -- Help text ---------------------------------------------------------------

#[test]
fn help_format_aligns_and_groups() {
    assert_eq!(
        parser_new().help_format(),
        "\
Usage: test [OPTIONS] [-- ...]

Test things.

Options:
  -h, --help         Print this help message
  -p, --path <PATH>  Set the path

Extra:
  Rarely used.

  --verbose          Print more
  -- ...             Pass the remaining arguments

Epilog."
    );
}

#[test]
fn help_format_shows_an_owned_description() {
    let mut parser: ArgumentParser<()> = ArgumentParser::new("prog");
    parser.argument_add(Argument::flag(
        "",
        "--level",
        format!("Set the level (default: {})", 3),
        Params::Count(0),
        |(), _| Ok(Step::Continue(0)),
    ));
    assert!(
        parser
            .help_format()
            .ends_with("--level     Set the level (default: 3)")
    );
}

/// A parser whose help flags are disabled, `-h` naming a host instead.
fn host_parser_new() -> ArgumentParser<Dest> {
    let mut parser = ArgumentParser::new("prog");
    parser.help_flags_set(false);
    parser.argument_add(Argument {
        metavar: "<HOST>",
        ..Argument::flag(
            "-h",
            "--host",
            "Connect to HOST",
            Params::Count(1),
            |dest: &mut Dest, values| {
                dest.path = Some(values[0].clone());
                Ok(Step::Continue(1))
            },
        )
    });
    parser
}

#[test]
fn help_flags_disabled_free_the_flags() {
    let mut parser = host_parser_new();
    let mut dest = Dest::default();
    parse_message(&mut parser, &mut dest, &args_from(&["-h", "example"])).unwrap();
    assert_eq!(dest.path.as_deref(), Some(OsStr::new("example")));
    assert_eq!(
        parse_message(&mut parser, &mut dest, &args_from(&["--help"])),
        Err("unknown argument '--help'".to_string())
    );
    assert_eq!(
        parser.help_format(),
        "Usage: prog [OPTIONS]\n\nOptions:\n  -h, --host <HOST>  Connect to HOST"
    );
}

#[test]
fn help_flags_disabled_leave_the_subcommands_answering_them() {
    let mut parser: ArgumentParser<Cmd> = ArgumentParser::new("cmd");
    parser.help_flags_set(false);
    parser.subparsers_add("Commands").parser_add("run", "");
    assert_eq!(
        parse_message(&mut parser, &mut Cmd::default(), &args_from(&["-h"])),
        Err("unknown argument '-h'".to_string())
    );
    let result = parser.parse(&mut Cmd::default(), &args_from(&["run", "-h"]));
    assert_eq!(format!("{result:?}"), r#"Ok(Help("cmd run"))"#);
}

#[test]
#[should_panic(expected = "The help flags are built in")]
fn help_flags_enabled_are_not_for_arguments() {
    let mut parser: ArgumentParser<()> = ArgumentParser::new("prog");
    parser.argument_add(Argument::flag("-h", "", "", Params::Count(0), |(), _| {
        Ok(Step::Continue(0))
    }));
}

#[test]
#[should_panic(expected = "An argument already uses the help flags")]
fn help_flags_enabled_after_an_argument_took_them() {
    host_parser_new().help_flags_set(true);
}

/// A parser with a `--mode` flag and a positional speed, both limited to
/// choices, the positional named by them.
fn choices_parser_new() -> ArgumentParser<Dest> {
    let mut parser = ArgumentParser::new("prog");
    parser.argument_add(Argument {
        metavar: "<MODE>",
        choices: &["fast", "slow"],
        ..Argument::flag(
            "",
            "--mode",
            "Set the mode",
            Params::Count(1),
            |dest: &mut Dest, values| {
                dest.path = Some(values[0].clone());
                Ok(Step::Continue(1))
            },
        )
    });
    parser.argument_add(Argument {
        choices: &["low", "high"],
        ..Argument::positional(
            "",
            "Set the speed",
            Params::Count(1),
            |dest: &mut Dest, values| {
                dest.rest = values.to_vec();
                Ok(Step::Continue(1))
            },
        )
    });
    parser
}

#[test]
fn parse_choices_accept_only_their_values() {
    let mut parser = choices_parser_new();
    let mut dest = Dest::default();
    parse_message(
        &mut parser,
        &mut dest,
        &args_from(&["--mode", "slow", "high"]),
    )
    .unwrap();
    assert_eq!(dest.path.as_deref(), Some(OsStr::new("slow")));
    assert_eq!(dest.rest, ["high"]);
    for args in [
        &["--mode", "warp", "high"][..],
        &["--mode=warp", "high"][..],
    ] {
        assert_eq!(
            parse_message(&mut parser, &mut Dest::default(), &args_from(args)),
            Err("'--mode': invalid choice 'warp' (choose from 'fast', 'slow')".to_string())
        );
    }
    assert_eq!(
        parse_message(&mut parser, &mut Dest::default(), &args_from(&["medium"])),
        Err("'{low,high}': invalid choice 'medium' (choose from 'low', 'high')".to_string())
    );
}

#[test]
fn help_format_names_values_by_their_choices() {
    // Unless a metavar names them, as for `--mode`.
    assert_eq!(
        choices_parser_new().help_format(),
        "\
Usage: prog [OPTIONS] {low,high}

Arguments:
  {low,high}     Set the speed

Options:
  -h, --help     Print this help message
  --mode <MODE>  Set the mode"
    );
}

#[test]
#[should_panic(expected = "Choices check counted values")]
fn choices_are_not_for_the_rest() {
    let mut parser: ArgumentParser<()> = ArgumentParser::new("prog");
    parser.argument_add(Argument {
        choices: &["a"],
        ..Argument::flag("", "--", "", Params::Rest, |(), values| {
            Ok(Step::Continue(values.len()))
        })
    });
}

#[test]
fn help_format_skips_empty_sections() {
    let parser: ArgumentParser<()> = ArgumentParser::new("prog");
    assert_eq!(
        parser.help_format(),
        "Usage: prog [OPTIONS]\n\nOptions:\n  -h, --help  Print this help message"
    );
}

// -- Positional arguments and `--flag=value` ---------------------------------

#[derive(Default)]
struct Cmd {
    command: Option<&'static str>,
    payload: Option<OsString>,
    import: Vec<OsString>,
    quiet: bool,
    rest: Vec<OsString>,
    /// Set by `--stop`, before it exits.
    stopped: bool,
}

fn quiet_argument() -> Argument<Cmd> {
    Argument::flag(
        "-q",
        "--quiet",
        "Print less",
        Params::Count(0),
        |dest: &mut Cmd, _| {
            dest.quiet = true;
            Ok(Step::Continue(0))
        },
    )
}

/// A parser with the subcommands `run <CODE> [--import <MODS>] [-- ...]` and
/// `ping`, the parent also takes `--quiet`.
fn cmd_parser_new() -> ArgumentParser<Cmd> {
    let mut parser = ArgumentParser::new("cmd");
    parser.argument_add(quiet_argument());
    let subparsers = parser.subparsers_add("Commands").required_set(true);
    let run = subparsers.parser_add("run", "Run code");
    run.descr_set("Run the code.")
        .defaults_set(|dest: &mut Cmd| dest.command = Some("run"));
    run.argument_add(Argument::positional(
        "<CODE>",
        "The code to run",
        Params::Count(1),
        |dest: &mut Cmd, values| {
            dest.payload = Some(values[0].clone());
            Ok(Step::Continue(1))
        },
    ));
    run.argument_add(Argument {
        metavar: "<MODS>",
        ..Argument::flag(
            "",
            "--import",
            "Import MODS first",
            Params::Count(1),
            |dest: &mut Cmd, values| {
                dest.import.push(values[0].clone());
                Ok(Step::Continue(1))
            },
        )
    });
    run.argument_add(quiet_argument());
    run.argument_add(Argument {
        metavar: "...",
        ..Argument::flag(
            "",
            "--",
            "Pass the remaining arguments",
            Params::Rest,
            |dest: &mut Cmd, values| {
                dest.rest = values.to_vec();
                Ok(Step::Continue(values.len()))
            },
        )
    });
    subparsers
        .parser_add("ping", "Check the server\nis running")
        .defaults_set(|dest: &mut Cmd| dest.command = Some("ping"));
    parser
}

fn cmd_parse(args: &[&str]) -> Result<Cmd, String> {
    cmd_parse_os(&args_from(args))
}

fn cmd_parse_os(args: &[OsString]) -> Result<Cmd, String> {
    let mut dest = Cmd::default();
    parse_message(&mut cmd_parser_new(), &mut dest, args)?;
    Ok(dest)
}

/// Return the help text asked for by `args`, if any.
fn cmd_help(args: &[&str]) -> Option<String> {
    let mut parser = cmd_parser_new();
    match parser.parse(&mut Cmd::default(), &args_from(args)) {
        Ok(Parsed::Help(parser)) => Some(parser.help_format()),
        _ => None,
    }
}

#[test]
fn parse_flag_value_attached_or_separate() {
    let dest = cmd_parse(&["run", "x", "--import=a", "--import", "b", "--import="]).unwrap();
    assert_eq!(dest.import, ["a", "b", ""]);
}

#[test]
fn parse_flag_value_attached_needs_one_value_flag() {
    assert_eq!(
        cmd_parse(&["run", "x", "--quiet=1"]).err(),
        Some("run: unknown argument '--quiet=1'".to_string())
    );
}

#[test]
fn parse_positional_accepts_empty_and_negative_values() {
    assert_eq!(
        cmd_parse(&["run", ""]).unwrap().payload.as_deref(),
        Some(OsStr::new(""))
    );
    assert_eq!(
        cmd_parse(&["run", "-1"]).unwrap().payload.as_deref(),
        Some(OsStr::new("-1"))
    );
    assert_eq!(
        cmd_parse(&["run", "-"]).unwrap().payload.as_deref(),
        Some(OsStr::new("-"))
    );
}

#[test]
fn parse_unknown_flag_is_not_a_positional_value() {
    assert_eq!(
        cmd_parse(&["run", "--bogus"]).err(),
        Some("run: unknown argument '--bogus'".to_string())
    );
}

#[test]
fn parse_positional_required() {
    assert_eq!(
        cmd_parse(&["run"]).err(),
        Some("run: '<CODE>' is required".to_string())
    );
}

#[test]
fn parse_extra_positional_fails() {
    assert_eq!(
        cmd_parse(&["run", "x", "y"]).err(),
        Some("run: unknown argument 'y'".to_string())
    );
}

// -- Subparsers --------------------------------------------------------------

#[test]
fn parse_subcommand_selects_and_parses_the_rest() {
    let dest = cmd_parse(&["-q", "run", "x", "--", "--import=a", "run"]).unwrap();
    assert_eq!(dest.command, Some("run"));
    assert_eq!(dest.payload.as_deref(), Some(OsStr::new("x")));
    assert!(dest.quiet);
    assert_eq!(dest.import, [] as [&str; 0]);
    assert_eq!(dest.rest, ["--import=a", "run"]);
}

#[test]
fn parse_options_after_the_subcommand_belong_to_it() {
    // The parent's `--quiet` is only accepted after the subcommand when the
    // subcommand defines it too, as with Python's `argparse`.
    assert!(cmd_parse(&["run", "x", "--quiet"]).unwrap().quiet);
    assert_eq!(
        cmd_parse(&["ping", "--quiet"]).err(),
        Some("ping: unknown argument '--quiet'".to_string())
    );
}

#[test]
fn parse_subcommand_not_selected_when_the_parent_fails() {
    let mut parser = cmd_parser_new();
    parser.argument_add(Argument {
        required: true,
        ..Argument::flag("", "--must", "", Params::Count(0), |_: &mut Cmd, _| {
            Ok(Step::Continue(0))
        })
    });
    let mut dest = Cmd::default();
    assert_eq!(
        parse_message(&mut parser, &mut dest, &args_from(&["ping"])),
        Err("'--must' is required".to_string())
    );
    assert_eq!(dest.command, None);
}

#[test]
fn parse_defaults_are_set_by_each_parser_used() {
    let mut parser = cmd_parser_new();
    parser.defaults_set(|dest: &mut Cmd| dest.quiet = true);
    let mut dest = Cmd::default();
    parse_message(&mut parser, &mut dest, &args_from(&["ping"])).unwrap();
    assert!(dest.quiet);
    assert_eq!(dest.command, Some("ping"));
}

#[test]
fn parse_subcommand_invalid() {
    assert_eq!(
        cmd_parse(&["jump"]).err(),
        Some("invalid subcommand 'jump' (choose from 'run', 'ping')".to_string())
    );
}

#[test]
fn parse_subcommand_required() {
    assert_eq!(
        cmd_parse(&["-q"]).err(),
        Some("a subcommand is required (choose from 'run', 'ping')".to_string())
    );
}

#[test]
fn parse_subcommand_optional() {
    let mut parser: ArgumentParser<Cmd> = ArgumentParser::new("prog");
    parser
        .subparsers_add("Commands")
        .parser_add("ping", "")
        .defaults_set(|dest: &mut Cmd| dest.command = Some("ping"));
    let mut dest = Cmd::default();
    assert_eq!(parse_message(&mut parser, &mut dest, &[]), Ok(()));
    assert_eq!(dest.command, None);
}

#[test]
fn parse_help_flag_selects_the_parser_it_follows() {
    assert!(
        cmd_help(&["run", "--help"])
            .unwrap()
            .starts_with("Usage: cmd run [OPTIONS] <CODE> [-- ...]")
    );
    assert!(
        cmd_help(&["-h", "run"])
            .unwrap()
            .starts_with("Usage: cmd [OPTIONS]")
    );
    assert_eq!(cmd_help(&["run", "x"]), None);
}

#[test]
fn parse_help_flag_stops_parsing() {
    // Help is answered even though the payload and its required value are
    // missing.
    assert!(cmd_help(&["run", "-h", "--import"]).is_some());
}

/// A parser whose `--stop` flag exits.
fn exit_parser_new() -> ArgumentParser<Cmd> {
    let mut parser = cmd_parser_new();
    parser.argument_add(Argument::flag(
        "",
        "--stop",
        "Stop parsing",
        Params::Count(0),
        |dest: &mut Cmd, _| {
            dest.stopped = true;
            Ok(Step::Exit)
        },
    ));
    parser
}

#[test]
fn parse_exit_stops_parsing() {
    // The required subcommand isn't reported, nor the unknown argument after
    // the flag, but the flag's callback has run.
    let mut parser = exit_parser_new();
    let mut dest = Cmd::default();
    let result = parser.parse(&mut dest, &args_from(&["--stop", "--bogus"]));
    assert_eq!(format!("{result:?}"), "Ok(Exit)");
    assert!(dest.stopped);
}

#[test]
fn parse_exit_after_an_error_is_not_reached() {
    let mut parser = exit_parser_new();
    let mut dest = Cmd::default();
    assert_eq!(
        parse_message(&mut parser, &mut dest, &args_from(&["--bogus", "--stop"])),
        Err("unknown argument '--bogus'".to_string())
    );
    assert!(!dest.stopped);
}

#[test]
fn parse_exit_from_a_subcommand() {
    // A subcommand's exit ends the whole parse, skipping its required payload.
    let mut parser: ArgumentParser<Cmd> = ArgumentParser::new("cmd");
    let run = parser
        .subparsers_add("Commands")
        .required_set(true)
        .parser_add("run", "");
    run.argument_add(Argument::positional(
        "<CODE>",
        "",
        Params::Count(1),
        |_: &mut Cmd, _| Ok(Step::Continue(1)),
    ));
    run.argument_add(Argument::flag(
        "",
        "--stop",
        "",
        Params::Count(0),
        |_: &mut Cmd, _| Ok(Step::Exit),
    ));
    let result = parser.parse(&mut Cmd::default(), &args_from(&["run", "--stop"]));
    assert_eq!(format!("{result:?}"), "Ok(Exit)");
}

#[test]
fn parse_error_holds_the_failing_parser() {
    let mut parser = cmd_parser_new();
    let e = parser
        .parse(&mut Cmd::default(), &args_from(&["run"]))
        .unwrap_err();
    assert_eq!(e.to_string(), "run: '<CODE>' is required");
    assert_eq!(
        e.parser.usage_format(),
        "Usage: cmd run [OPTIONS] <CODE> [-- ...]"
    );
    assert_eq!(
        e.error_format(),
        "Usage: cmd run [OPTIONS] <CODE> [-- ...]\nError: run: '<CODE>' is required"
    );
}

#[test]
fn parse_result_debug_names_the_parser() {
    let mut parser = cmd_parser_new();
    let result = parser.parse(&mut Cmd::default(), &args_from(&["run", "-h"]));
    assert_eq!(format!("{result:?}"), r#"Ok(Help("cmd run"))"#);
    let result = parser.parse(&mut Cmd::default(), &args_from(&["jump"]));
    assert_eq!(
        format!("{result:?}"),
        r#"Err(ParseError { message: "invalid subcommand 'jump' (choose from 'run', 'ping')", parser: "cmd" })"#
    );
}

#[test]
fn help_format_lists_subcommands_before_options() {
    assert_eq!(
        cmd_parser_new().help_format(),
        "\
Usage: cmd [OPTIONS] <COMMAND> ...

Commands:
  run          Run code
  ping         Check the server
               is running

Options:
  -h, --help   Print this help message
  -q, --quiet  Print less"
    );
}

#[test]
fn help_format_lists_positionals_first() {
    assert_eq!(
        cmd_help(&["run", "-h"]).unwrap(),
        "\
Usage: cmd run [OPTIONS] <CODE> [-- ...]

Run the code.

Arguments:
  <CODE>           The code to run

Options:
  -h, --help       Print this help message
  --import <MODS>  Import MODS first
  -q, --quiet      Print less
  -- ...           Pass the remaining arguments"
    );
}

#[test]
fn help_format_usage_lists_required_flags_and_optional_positionals() {
    let mut parser: ArgumentParser<()> = ArgumentParser::new("prog");
    parser.argument_add(Argument {
        metavar: "<FILE>",
        required: true,
        ..Argument::flag("-i", "--input", "", Params::Count(1), |(), _| {
            Ok(Step::Continue(1))
        })
    });
    parser.argument_add(Argument {
        required: false,
        ..Argument::positional("<NAME>", "", Params::Rest, |(), values| {
            Ok(Step::Continue(values.len()))
        })
    });
    assert!(
        parser
            .help_format()
            .starts_with("Usage: prog [OPTIONS] --input <FILE> [<NAME> ...]\n")
    );
}

#[test]
#[should_panic(expected = "The callback left its attached value unused")]
fn parse_flag_value_attached_must_be_used() {
    let mut parser: ArgumentParser<()> = ArgumentParser::new("prog");
    parser.argument_add(Argument::flag(
        "",
        "--level",
        "",
        Params::Count(1),
        |(), _| Ok(Step::Continue(0)),
    ));
    let _ = parser.parse(&mut (), &args_from(&["--level=1"]));
}

// -- Values that aren't valid UTF-8 ------------------------------------------

// Invalid UTF-8 is built from raw bytes, which only Unix can turn into an
// `OsString`.
#[cfg(unix)]
mod non_utf8 {
    use super::*;
    use std::os::unix::ffi::OsStringExt;

    fn os_from(bytes: &[u8]) -> OsString {
        OsString::from_vec(bytes.to_vec())
    }

    #[test]
    fn parse_values_keep_bytes_that_are_not_utf8() {
        let mut parser = parser_new();
        let mut dest = Dest::default();
        let args = [
            OsString::from("--path"),
            os_from(b"a\xffb"),
            OsString::from("--"),
            os_from(b"\xfe"),
        ];
        parse_message(&mut parser, &mut dest, &args).unwrap();
        assert_eq!(dest.path, Some(os_from(b"a\xffb")));
        assert_eq!(dest.rest, [os_from(b"\xfe")]);

        // Attached to its flag, and as a positional value.
        let dest = cmd_parse_os(&[
            OsString::from("run"),
            os_from(b"\xff"),
            os_from(b"--import=\xc3=\xe9"),
        ])
        .unwrap();
        assert_eq!(dest.payload, Some(os_from(b"\xff")));
        assert_eq!(dest.import, [os_from(b"\xc3=\xe9")]);
    }

    #[test]
    fn parse_words_that_are_not_utf8_name_no_flag_or_subcommand() {
        assert_eq!(
            cmd_parse_os(&[os_from(b"-\xff")]).err(),
            Some("unknown argument '-\u{fffd}'".to_string())
        );
        assert_eq!(
            cmd_parse_os(&[os_from(b"run\xff")]).err(),
            Some("invalid subcommand 'run\u{fffd}' (choose from 'run', 'ping')".to_string())
        );
    }

    #[test]
    fn parse_choices_refuse_a_value_that_is_not_utf8() {
        let mut parser = choices_parser_new();
        assert_eq!(
            parse_message(
                &mut parser,
                &mut Dest::default(),
                &[OsString::from("--mode"), os_from(b"fast\xff")],
            ),
            Err("'--mode': invalid choice 'fast\u{fffd}' (choose from 'fast', 'slow')".to_string())
        );
    }

    #[test]
    fn value_to_str_names_the_invalid_value() {
        assert_eq!(value_to_str(OsStr::new("a")), Ok("a"));
        assert_eq!(
            value_to_str(&os_from(b"a\xffb")),
            Err("'a\u{fffd}b' is not valid UTF-8".to_string())
        );
    }
}
