// SPDX-License-Identifier: MIT

//! A small command-line argument parser, modeled on Python's `argparse`.
//!
//! Each argument is matched by its flag (or its position) and hands its values
//! to a callback, which stores them in a destination the caller passes to
//! [`ArgumentParser::parse`]. Subcommands each have their own parser (see
//! [`ArgumentParser::subparsers_add`]). The help text is generated from the
//! same definitions - starting with a usage line - and every parser answers
//! `-h` / `--help` with its own, unless it's told not to (see
//! [`ArgumentParser::help_flags_set`]).
//!
//! Arguments are `OsString`s, as `std::env::args_os()` returns them, so a
//! value that isn't valid UTF-8 (such as a path) reaches its callback intact.
//! Flags and subcommand names are UTF-8, so only a word that is can match one.

use std::borrow::Cow;
use std::ffi::{OsStr, OsString};

/// Opaque handle to an argument group, which gathers arguments under a
/// heading in the help text.
#[derive(PartialEq, Eq, Debug, Copy, Clone)]
pub struct ArgGroup(usize);

struct ArgGroupData {
    name: &'static str,
    descr: &'static str,
}

/// The number of values an argument takes.
#[derive(PartialEq, Eq, Debug, Copy, Clone)]
pub enum Params {
    /// Exactly this many values must be given, although the callback may use
    /// fewer. They are the words that follow, whatever they look like.
    Count(usize),
    /// Every remaining argument is passed to the callback.
    Rest,
}

/// What a callback did, see [`Callback`].
#[derive(PartialEq, Eq, Debug, Copy, Clone)]
pub enum Step {
    /// It used this many of its values, parsing continues after them.
    ///
    /// NOTE: most callbacks use every value they are given, so the count can
    /// look redundant. Keep it: it's what lets an argument take a variable
    /// number of values - with [`Params::Rest`] a callback may use values up
    /// to the next flag (as Python's `nargs='*'`), leaving the rest to be
    /// parsed.
    Continue(usize),
    /// It did what the argument is for (such as printing a version), so
    /// parsing stops: nothing after it is parsed or checked, and
    /// [`ArgumentParser::parse`] returns [`Parsed::Exit`]. This exit is a
    /// success, a callback fails by returning an error instead.
    Exit,
}

/// Store an argument's values in the destination.
///
/// Receives the values of the argument (see [`Params`]) and returns what it
/// did with them (see [`Step`]), or a reason the values are invalid.
pub type Callback<T> = Box<dyn FnMut(&mut T, &[OsString]) -> Result<Step, String>>;

/// Set values in the destination, see [`ArgumentParser::defaults_set`].
type DefaultsCallback<T> = Box<dyn FnMut(&mut T)>;

/// An argument definition, see [`ArgumentParser::argument_add`].
///
/// An argument without flags is positional: positional arguments take the
/// values that aren't flags, in the order they are added.
///
/// Create one with [`Self::flag`] or [`Self::positional`], setting the other
/// fields with struct update syntax:
/// `Argument { metavar: "<PATH>", ..Argument::flag(..) }`.
pub struct Argument<T> {
    /// Short flag (e.g. `-h`), may be empty.
    pub id_short: &'static str,
    /// Long flag (e.g. `--help`), may be empty. A long flag taking one value
    /// also accepts it as `--flag=value`.
    pub id_long: &'static str,
    /// Name of the values in the help text (e.g. `<PATH>`), may be empty
    /// unless the argument is positional without `choices`. When empty, the
    /// `choices` name the values instead (as `{a,b}`).
    pub metavar: &'static str,
    /// Description in the help text, owned when it's built at run time (such
    /// as from a default it names).
    pub descr: Cow<'static, str>,
    pub callback: Callback<T>,
    pub params: Params,
    /// The values the argument accepts, any when empty (as Python's
    /// `choices`). Each value is checked before the callback runs, which is
    /// only possible for [`Params::Count`].
    pub choices: &'static [&'static str],
    /// Fail parsing when the argument isn't given.
    pub required: bool,
    /// The help text section, ungrouped arguments are listed under
    /// "Arguments" (positional) or "Options".
    pub group: Option<ArgGroup>,
}

impl<T> Argument<T> {
    /// Create an optional argument with no metavar, in no group.
    pub fn flag(
        id_short: &'static str,
        id_long: &'static str,
        descr: impl Into<Cow<'static, str>>,
        params: Params,
        callback: impl FnMut(&mut T, &[OsString]) -> Result<Step, String> + 'static,
    ) -> Self {
        Self {
            id_short,
            id_long,
            metavar: "",
            descr: descr.into(),
            callback: Box::new(callback),
            params,
            choices: &[],
            required: false,
            group: None,
        }
    }

    /// Create a required positional argument, in no group.
    pub fn positional(
        metavar: &'static str,
        descr: impl Into<Cow<'static, str>>,
        params: Params,
        callback: impl FnMut(&mut T, &[OsString]) -> Result<Step, String> + 'static,
    ) -> Self {
        Self {
            id_short: "",
            id_long: "",
            metavar,
            descr: descr.into(),
            callback: Box::new(callback),
            params,
            choices: &[],
            required: true,
            group: None,
        }
    }

    fn is_positional(&self) -> bool {
        self.id_short.is_empty() && self.id_long.is_empty()
    }

    /// Return true when either flag is one of the built-in help flags.
    fn uses_help_flags(&self) -> bool {
        [self.id_short, self.id_long]
            .iter()
            .any(|id| [HELP_ID_SHORT, HELP_ID_LONG].contains(id))
    }

    /// Return the flag of this argument that `word` is, if any.
    fn flag_matched(&self, word: &OsStr) -> Option<&'static str> {
        [self.id_short, self.id_long]
            .into_iter()
            .find(|id| !id.is_empty() && word == *id)
    }

    /// Return the value attached to this argument's long flag in `word`, as in
    /// `--flag=value`, when it takes one value.
    fn value_attached(&self, word: &OsStr) -> Option<OsString> {
        if !self.id_long.starts_with("--") || self.params != Params::Count(1) {
            return None;
        }
        let value = word
            .as_encoded_bytes()
            .strip_prefix(self.id_long.as_bytes())?
            .strip_prefix(b"=")?;
        // SAFETY: `value` follows `=`, so the split is right after a non-empty
        // UTF-8 substring, which `from_encoded_bytes_unchecked` allows.
        Some(unsafe { OsStr::from_encoded_bytes_unchecked(value) }.to_owned())
    }

    /// Return the name of the values: the metavar, or else the choices.
    fn metavar_display(&self) -> Cow<'static, str> {
        if self.metavar.is_empty() && !self.choices.is_empty() {
            Cow::Owned(format!("{{{}}}", self.choices.join(",")))
        } else {
            Cow::Borrowed(self.metavar)
        }
    }

    /// Return the name to show in errors, the flags are joined with `sep`.
    fn name_display(&self, sep: &str) -> String {
        if self.is_positional() {
            self.metavar_display().into_owned()
        } else if self.id_short.is_empty() || self.id_long.is_empty() {
            format!("{}{}", self.id_short, self.id_long)
        } else {
            format!("{}{sep}{}", self.id_short, self.id_long)
        }
    }
}

/// Subcommands of a parser, see [`ArgumentParser::subparsers_add`].
///
/// Every parser has them, a parser without subcommands has none added.
///
/// The first argument that isn't a flag of the parent (or one of its
/// positional arguments) selects a subcommand, every argument after it is
/// parsed by that subcommand's parser.
pub struct Subparsers<T> {
    /// The parent's program name, which each subcommand's extends.
    prog: Cow<'static, str>,
    title: &'static str,
    descr: &'static str,
    required: bool,
    parsers: Vec<Subparser<T>>,
}

struct Subparser<T> {
    name: &'static str,
    help: &'static str,
    parser: ArgumentParser<T>,
}

impl<T> Subparsers<T> {
    /// Set the description following the title of the subcommands in the help
    /// text (empty by default).
    pub fn descr_set(&mut self, descr: &'static str) -> &mut Self {
        self.descr = descr;
        self
    }

    /// Set whether parsing fails when no subcommand is given (it doesn't by
    /// default, as with Python's `argparse`).
    pub fn required_set(&mut self, required: bool) -> &mut Self {
        self.required = required;
        self
    }

    /// Add a subcommand, returning its parser.
    ///
    /// `help` describes the subcommand in the parent's help text. Its own help
    /// text has no description or epilog unless they're set on its parser (see
    /// [`ArgumentParser::descr_set`]), and its usage line names it after the
    /// parent's program name.
    pub fn parser_add(&mut self, name: &'static str, help: &'static str) -> &mut ArgumentParser<T> {
        debug_assert!(!name.is_empty(), "A subcommand needs a name");
        debug_assert!(
            !self.parsers.iter().any(|subparser| subparser.name == name),
            "The subcommand name is already used"
        );
        self.parsers.push(Subparser {
            name,
            help,
            parser: ArgumentParser {
                prog: Cow::Owned(format!("{} {name}", self.prog)),
                ..ArgumentParser::new("")
            },
        });
        let index = self.parsers.len() - 1;
        &mut self.parsers[index].parser
    }

    /// Return the subcommand names quoted, for error messages.
    fn names_join(&self) -> String {
        names_quote(self.parsers.iter().map(|subparser| subparser.name))
    }
}

/// Return `names` quoted and comma-separated, for error messages.
fn names_quote<'a>(names: impl IntoIterator<Item = &'a str>) -> String {
    names
        .into_iter()
        .map(|name| format!("'{name}'"))
        .collect::<Vec<_>>()
        .join(", ")
}

/// The built-in help flags.
const HELP_ID_SHORT: &str = "-h";
const HELP_ID_LONG: &str = "--help";

/// The outcome of a successful [`ArgumentParser::parse`].
pub enum Parsed<'a, T> {
    /// Every argument was parsed.
    Done,
    /// Help was asked for, parsing stopped at the flag. Holds the parser
    /// (or subcommand's parser) to print the help of.
    Help(&'a ArgumentParser<T>),
    /// A callback stopped parsing (see [`Step::Exit`]).
    Exit,
}

/// A parse failure, see [`ArgumentParser::parse`].
pub struct ParseError<'a, T> {
    /// What failed. An error from a subcommand's parser is prefixed with the
    /// subcommand's name.
    pub message: String,
    /// The parser (or subcommand's parser) that failed, to print its help.
    pub parser: &'a ArgumentParser<T>,
}

// The `Debug` impls show a parser as its program name, so `T` needn't be
// `Debug` for a parse result to be unwrapped.
impl<T> std::fmt::Debug for Parsed<'_, T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Done => f.write_str("Done"),
            Self::Help(parser) => f.debug_tuple("Help").field(&parser.prog).finish(),
            Self::Exit => f.write_str("Exit"),
        }
    }
}

impl<T> std::fmt::Debug for ParseError<'_, T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ParseError")
            .field("message", &self.message)
            .field("parser", &self.parser.prog)
            .finish()
    }
}

impl<T> ParseError<'_, T> {
    /// Return what to print for the failure: the failing parser's usage line
    /// followed by the message (as Python's `argparse` prints it).
    #[must_use]
    pub fn error_format(&self) -> String {
        format!("{}\nError: {}", self.parser.usage_format(), self.message)
    }
}

impl<T> std::fmt::Display for ParseError<'_, T> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

/// Where [`ArgumentParser::parse_args`] reached the end of its arguments.
enum ParseStep {
    Done,
    /// The subcommand at `index` parses the arguments from `args_start`.
    Subcommand {
        index: usize,
        args_start: usize,
    },
}

/// Why [`ArgumentParser::parse_args`] stopped before the end of its arguments.
///
/// Stopping to print help or to exit takes the same path as an error, so `?`
/// ends the parse wherever a callback runs.
enum Halt {
    Error(String),
    /// A help flag was given.
    Help,
    /// A callback returned [`Step::Exit`].
    Exit,
}

impl From<String> for Halt {
    fn from(message: String) -> Self {
        Self::Error(message)
    }
}

pub struct ArgumentParser<T> {
    arguments: Vec<Argument<T>>,
    groups: Vec<ArgGroupData>,
    subparsers: Subparsers<T>,
    defaults: Vec<DefaultsCallback<T>>,
    prog: Cow<'static, str>,
    descr: &'static str,
    epilog: &'static str,
    /// Whether `-h` / `--help` ask for this parser's help.
    help_flags: bool,
}

/// Return `value` as UTF-8, for a callback taking a value that must be text.
///
/// # Errors
///
/// Fails on a value that isn't valid UTF-8, naming it (lossily).
pub fn value_to_str(value: &OsStr) -> Result<&str, String> {
    value
        .to_str()
        .ok_or_else(|| format!("'{}' is not valid UTF-8", value.display()))
}

/// Return true when `word` reads as a flag rather than a value.
///
/// A negative number (such as `-1` or `-.5`) is a value rather than an
/// unknown flag.
fn is_flag_like(word: &OsStr) -> bool {
    match word.as_encoded_bytes() {
        [b'-', first, ..] => !(first.is_ascii_digit() || *first == b'.'),
        _ => false,
    }
}

/// Return the values an argument takes from the front of `args`.
///
/// Values are taken as they are, even when they look like flags (as with
/// `getopt`), so `-T -foo` gives `-foo` to `-T`.
fn values_take<'a>(
    params: Params,
    name: &str,
    args: &'a [OsString],
) -> Result<&'a [OsString], String> {
    match params {
        Params::Rest => Ok(args),
        Params::Count(count) => {
            let given = args.len();
            if given < count {
                return Err(format!(
                    "'{name}' requires {count} value{}, {given} given",
                    if count == 1 { "" } else { "s" },
                ));
            }
            Ok(&args[..count])
        }
    }
}

/// Fail when a required argument isn't `used`.
///
/// Takes the arguments rather than the parser, so a caller may hold its
/// subparsers meanwhile.
fn required_check<T>(arguments: &[Argument<T>], used: &[bool]) -> Result<(), String> {
    match arguments
        .iter()
        .zip(used)
        .find(|(argument, used)| argument.required && !**used)
    {
        Some((argument, _)) => Err(format!("'{}' is required", argument.name_display("/"))),
        None => Ok(()),
    }
}

/// Format one entry of the help text, indenting the lines of a multi-line
/// description to line up with its first.
fn help_line(column: &str, width: usize, descr: &str) -> String {
    let indent = format!("\n{:width$}", "", width = width + 4);
    format!("  {column:<width$}  {}", descr.replace('\n', &indent))
}

impl<T> ArgumentParser<T> {
    /// Create a parser for the program `prog`, which leads the usage line.
    #[must_use]
    pub fn new(prog: &'static str) -> Self {
        Self {
            arguments: Vec::new(),
            groups: Vec::new(),
            subparsers: Subparsers {
                prog: Cow::Borrowed(""),
                title: "",
                descr: "",
                required: false,
                parsers: Vec::new(),
            },
            defaults: Vec::new(),
            prog: Cow::Borrowed(prog),
            descr: "",
            epilog: "",
            help_flags: true,
        }
    }

    /// Set the description following the usage line in the help text (empty
    /// by default).
    pub fn descr_set(&mut self, descr: &'static str) -> &mut Self {
        self.descr = descr;
        self
    }

    /// Set the epilog ending the help text (empty by default).
    pub fn epilog_set(&mut self, epilog: &'static str) -> &mut Self {
        self.epilog = epilog;
        self
    }

    /// Set whether `-h` / `--help` ask for this parser's help (they do by
    /// default). Disabling them (as Python's `add_help=False`) leaves the flags
    /// free for arguments of the parser's own, and drops them from the help.
    ///
    /// A subcommand's parser has its own setting, so disabling the flags on a
    /// parent leaves its subcommands answering them.
    pub fn help_flags_set(&mut self, enabled: bool) -> &mut Self {
        debug_assert!(
            !enabled || !self.arguments.iter().any(Argument::uses_help_flags),
            "An argument already uses the help flags"
        );
        self.help_flags = enabled;
        self
    }

    /// Add a group, listed in the help text after the ungrouped arguments
    /// in the order groups are added.
    #[must_use]
    pub fn group_add(&mut self, name: &'static str, descr: &'static str) -> ArgGroup {
        self.groups.push(ArgGroupData { name, descr });
        ArgGroup(self.groups.len() - 1)
    }

    /// Add an argument, see [`Argument`].
    pub fn argument_add(&mut self, argument: Argument<T>) {
        debug_assert!(
            !argument.is_positional() || !argument.metavar_display().is_empty(),
            "A positional argument needs a metavar (or choices)"
        );
        debug_assert!(
            argument.choices.is_empty() || matches!(argument.params, Params::Count(_)),
            "Choices check counted values, not the rest of the arguments"
        );
        debug_assert!(
            !argument.is_positional() || argument.params != Params::Count(0),
            "A positional argument needs a value"
        );
        debug_assert!(
            argument
                .group
                .is_none_or(|group| group.0 < self.groups.len()),
            "The argument group belongs to another parser"
        );
        debug_assert!(
            !self.help_flags || !argument.uses_help_flags(),
            "The help flags are built in (see `help_flags_set`)"
        );
        debug_assert!(
            !self.arguments.iter().any(|other| {
                [argument.id_short, argument.id_long]
                    .iter()
                    .any(|id| other.flag_matched(OsStr::new(id)).is_some())
            }),
            "The argument's flag is already used"
        );
        self.arguments.push(argument);
    }

    /// Add subcommands, returning them for [`Subparsers::parser_add`].
    ///
    /// `title` heads the subcommands in the help text. A parser has at most
    /// one set of subcommands. To tell which subcommand was selected, set a
    /// value with each subcommand's [`Self::defaults_set`].
    pub fn subparsers_add(&mut self, title: &'static str) -> &mut Subparsers<T> {
        debug_assert!(
            self.subparsers.parsers.is_empty(),
            "The subparsers are already added"
        );
        self.subparsers = Subparsers {
            prog: self.prog.clone(),
            title,
            descr: "",
            required: false,
            parsers: Vec::new(),
        };
        &mut self.subparsers
    }

    /// Set values in the destination whenever this parser parses, before any
    /// of its arguments (as Python's `set_defaults`).
    ///
    /// A subcommand's parser parses only once it's selected, so this is how to
    /// record which subcommand was (e.g. as an enum, to dispatch on).
    pub fn defaults_set(&mut self, callback: impl FnMut(&mut T) + 'static) -> &mut Self {
        self.defaults.push(Box::new(callback));
        self
    }

    /// Run an argument's callback on its values, returning how many it used.
    fn callback_run(
        &mut self,
        index: usize,
        dest: &mut T,
        name: &str,
        values: &[OsString],
    ) -> Result<usize, Halt> {
        let choices = self.arguments[index].choices;
        if !choices.is_empty()
            && let Some(value) = values
                .iter()
                .find(|value| !choices.iter().any(|choice| *value == *choice))
        {
            return Err(Halt::Error(format!(
                "'{name}': invalid choice '{}' (choose from {})",
                value.display(),
                names_quote(choices.iter().copied())
            )));
        }
        let step =
            (self.arguments[index].callback)(dest, values).map_err(|e| format!("'{name}': {e}"))?;
        let Step::Continue(values_used) = step else {
            return Err(Halt::Exit);
        };
        debug_assert!(
            values_used <= values.len(),
            "The callback used more values than given"
        );
        Ok(values_used)
    }

    /// Parse `args` (without the program name), running each argument's
    /// callback on `dest`.
    ///
    /// # Errors
    ///
    /// Fails on an unknown argument or subcommand, missing values, a callback
    /// rejecting its values, or a required argument (or subcommand) that isn't
    /// given.
    pub fn parse(
        &mut self,
        dest: &mut T,
        args: &[OsString],
    ) -> Result<Parsed<'_, T>, ParseError<'_, T>> {
        match self.parse_args(dest, args) {
            Ok(ParseStep::Done) => Ok(Parsed::Done),
            Ok(ParseStep::Subcommand { index, args_start }) => {
                let subparser = &mut self.subparsers.parsers[index];
                let name = subparser.name;
                subparser
                    .parser
                    .parse(dest, &args[args_start..])
                    .map_err(|e| ParseError {
                        message: format!("{name}: {}", e.message),
                        parser: e.parser,
                    })
            }
            Err(Halt::Help) => Ok(Parsed::Help(self)),
            Err(Halt::Exit) => Ok(Parsed::Exit),
            Err(Halt::Error(message)) => Err(ParseError {
                message,
                parser: self,
            }),
        }
    }

    /// Parse the arguments of this parser, up to a subcommand.
    fn parse_args(&mut self, dest: &mut T, args: &[OsString]) -> Result<ParseStep, Halt> {
        for callback in &mut self.defaults {
            callback(dest);
        }
        let mut used = vec![false; self.arguments.len()];

        let mut i = 0;
        while i < args.len() {
            let word = args[i].as_os_str();

            if self.help_flags && (word == HELP_ID_SHORT || word == HELP_ID_LONG) {
                return Err(Halt::Help);
            }

            // A flag, its values follow as separate words.
            if let Some((index, flag)) = self
                .arguments
                .iter()
                .enumerate()
                .find_map(|(index, argument)| Some((index, argument.flag_matched(word)?)))
            {
                used[index] = true;
                i += 1;
                let values = values_take(self.arguments[index].params, flag, &args[i..])?;
                i += self.callback_run(index, dest, flag, values)?;
                continue;
            }

            // A long flag with its value attached, as `--flag=value`.
            if let Some((index, value)) = self
                .arguments
                .iter()
                .enumerate()
                .find_map(|(index, argument)| Some((index, argument.value_attached(word)?)))
            {
                used[index] = true;
                i += 1;
                let flag = self.arguments[index].id_long;
                let values_used = self.callback_run(index, dest, flag, &[value])?;
                // An attached value can't be left to parse as an argument of
                // its own, it would be dropped.
                debug_assert_eq!(
                    values_used, 1,
                    "The callback left its attached value unused"
                );
                continue;
            }

            if is_flag_like(word) {
                return Err(Halt::Error(format!(
                    "unknown argument '{}'",
                    word.display()
                )));
            }

            // The next positional argument not yet given.
            if let Some(index) = (0..self.arguments.len())
                .find(|&index| self.arguments[index].is_positional() && !used[index])
            {
                used[index] = true;
                let name = self.arguments[index].metavar_display();
                let values = values_take(self.arguments[index].params, &name, &args[i..])?;
                i += self.callback_run(index, dest, &name, values)?;
                continue;
            }

            // A subcommand, which parses every argument after it. This
            // parser's arguments are all given by then, so check them first.
            let subparsers = &self.subparsers;
            let Some(index) = subparsers
                .parsers
                .iter()
                .position(|subparser| word == subparser.name)
            else {
                return Err(Halt::Error(if subparsers.parsers.is_empty() {
                    format!("unknown argument '{}'", word.display())
                } else {
                    format!(
                        "invalid subcommand '{}' (choose from {})",
                        word.display(),
                        subparsers.names_join()
                    )
                }));
            };
            required_check(&self.arguments, &used)?;
            return Ok(ParseStep::Subcommand {
                index,
                args_start: i + 1,
            });
        }

        required_check(&self.arguments, &used)?;
        if self.subparsers.required {
            return Err(Halt::Error(format!(
                "a subcommand is required (choose from {})",
                self.subparsers.names_join()
            )));
        }
        Ok(ParseStep::Done)
    }

    /// Return the usage line, summarizing the command line. It leads the help
    /// text, and the text of a failure (see [`ParseError::error_format`]).
    ///
    /// Optional flags are summarized as `[OPTIONS]`, with the exception of
    /// those taking the remaining arguments (e.g. `--`), which are shown last
    /// since nothing can follow them.
    #[must_use]
    pub fn usage_format(&self) -> String {
        let mut parts = vec![self.prog.to_string(), "[OPTIONS]".to_string()];
        let flags = self
            .arguments
            .iter()
            .filter(|argument| !argument.is_positional());
        let positionals = self
            .arguments
            .iter()
            .filter(|argument| argument.is_positional());
        let flag_usage = |argument: &Argument<T>| {
            let flag = if argument.id_long.is_empty() {
                argument.id_short
            } else {
                argument.id_long
            };
            let metavar = argument.metavar_display();
            if metavar.is_empty() {
                flag.to_string()
            } else {
                format!("{flag} {metavar}")
            }
        };
        parts.extend(
            flags
                .clone()
                .filter(|argument| argument.required)
                .map(flag_usage),
        );
        parts.extend(positionals.map(|argument| {
            let usage = if argument.params == Params::Rest {
                format!("{} ...", argument.metavar_display())
            } else {
                argument.metavar_display().into_owned()
            };
            if argument.required {
                usage
            } else {
                format!("[{usage}]")
            }
        }));
        if !self.subparsers.parsers.is_empty() {
            parts.push(if self.subparsers.required {
                "<COMMAND> ...".to_string()
            } else {
                "[<COMMAND> ...]".to_string()
            });
        }
        parts.extend(
            flags
                .filter(|argument| !argument.required && argument.params == Params::Rest)
                .map(|argument| format!("[{}]", flag_usage(argument))),
        );
        format!("Usage: {}", parts.join(" "))
    }

    /// Return the help text, without a trailing newline.
    #[must_use]
    pub fn help_format(&self) -> String {
        let columns: Vec<String> = self
            .arguments
            .iter()
            .map(|argument| {
                let metavar = argument.metavar_display();
                if argument.is_positional() || metavar.is_empty() {
                    argument.name_display(", ")
                } else {
                    format!("{} {metavar}", argument.name_display(", "))
                }
            })
            .collect();
        let help_column = self
            .help_flags
            .then(|| format!("{HELP_ID_SHORT}, {HELP_ID_LONG}"));
        let subparsers = &self.subparsers;
        let width = columns
            .iter()
            .chain(&help_column)
            .map(String::len)
            .chain(
                subparsers
                    .parsers
                    .iter()
                    .map(|subparser| subparser.name.len()),
            )
            .max()
            .unwrap_or(0);

        // Format a section of arguments, `None` when it has none.
        let section_format = |name: &str, descr: &str, mut lines: Vec<String>| -> Option<String> {
            if lines.is_empty() {
                return None;
            }
            if !descr.is_empty() {
                lines.insert(0, format!("  {descr}\n"));
            }
            lines.insert(0, format!("{name}:"));
            Some(lines.join("\n"))
        };
        let arguments_format = |group: Option<ArgGroup>, positional: Option<bool>| -> Vec<String> {
            self.arguments
                .iter()
                .zip(&columns)
                .filter(|(argument, _)| {
                    argument.group == group
                        && positional
                            .is_none_or(|positional| argument.is_positional() == positional)
                })
                .map(|(argument, column)| help_line(column, width, &argument.descr))
                .collect()
        };

        // Positional arguments and subcommands come first (as Python's
        // `argparse` does), then the ungrouped options, then each group.
        let mut sections: Vec<Option<String>> = vec![
            Some(self.usage_format()),
            (!self.descr.is_empty()).then(|| self.descr.to_string()),
            section_format("Arguments", "", arguments_format(None, Some(true))),
        ];
        let lines = subparsers
            .parsers
            .iter()
            .map(|subparser| help_line(subparser.name, width, subparser.help))
            .collect();
        sections.push(section_format(subparsers.title, subparsers.descr, lines));
        let mut options = arguments_format(None, Some(false));
        if let Some(help_column) = &help_column {
            options.insert(0, help_line(help_column, width, "Print this help message"));
        }
        sections.push(section_format("Options", "", options));
        for (index, group) in self.groups.iter().enumerate() {
            sections.push(section_format(
                group.name,
                group.descr,
                arguments_format(Some(ArgGroup(index)), None),
            ));
        }
        sections.push((!self.epilog.is_empty()).then(|| self.epilog.to_string()));
        sections
            .into_iter()
            .flatten()
            .collect::<Vec<_>>()
            .join("\n\n")
    }
}

#[cfg(test)]
#[path = "tests/lib_tests.rs"]
mod tests;
