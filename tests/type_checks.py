from typing import (
    Any,
    Final,
    Iterable,
    Literal,
    assert_type,
)

import errorz as rz
from errorz import Err, Result

MYPY: Final = True
PYRIGHT: Literal[False] = False
EXPECTED: Literal[False] = False


E = Exception


def add(x: int | float, y: int | float) -> float:
    return float(x + y)


def mk[T](x: T) -> Result[T, E]:
    return x


def assert_errorz_types() -> None:
    """
    This is a manual check to ensure that the type checking is working as expected.

    If someone knowns how to automatically test the revealed type, please let me know ;)
    """
    i = mk(1)
    f = mk(1.0)
    e: Result[int, E] = rz.err(E("error"))

    #
    # Basic tests
    #
    assert_type(rz.is_err(i), bool)
    assert_type(rz.check(i), bool)

    #
    # Unwraps
    #
    assert_type(rz.unwrap(i), int)
    assert_type(rz.unwrap_lazy(i, lambda: 42), int)

    # Pyright is too agresssive with type narrowing and can lead to false negatives
    if PYRIGHT:
        assert_type(rz.unwrap(e), Err[E])
    else:
        assert_type(rz.unwrap(e), int)  # pyright: ignore[reportAssertTypeFailure]

    assert_type(rz.expect(i, "error"), int)
    assert_type(rz.to_optional(i), int | None)

    #
    # Mapping functions
    #
    def f_3(x: int, y: int, z: int) -> float:
        return float(x + y + z)

    assert_type(rz.map(float, i), Result[float, E])
    assert_type(rz.map(add, i, i), Result[float, E])
    assert_type(rz.map(add, f, i), Result[float, E])
    assert_type(rz.map(f_3, i, i, i), Result[float, E])

    #
    # Zips, coallesces, etc
    #

    # Mypy has a hard time with type inference here. It expects that coalesce
    # accept only Err[Never] cases.
    assert_type(rz.coalesce(f, i), Result[int | float, E])
    assert_type(rz.coalesce(e, i), Result[int, E])
    assert_type(rz.coalesce(f, i, e), Result[int | float, E])
    assert_type(rz.zip(i, i), tuple[int, int] | Err[E])

    #
    # Sequences
    #
    assert_type(rz.filter([i, e, i]), Iterable[int])

    #
    # Arithmetic
    #
    assert_type(((i + 1) * i - 1) / 2, Result[float, E])

    #
    # Functions
    #
    def f2[T](x: Result[T], y: Result[T]) -> Result[T]:
        return x if rz.is_ok(x) else y

    assert_type(f2(i, i), Result[int, Any])

    def id[T, E](x: Result[T, E]) -> Result[T, E]:
        return x

    assert_type(id(i), Result[int, E])


def assert_boolean_narrowing() -> None:
    class Foo:
        def __bool__(self) -> Literal[True]:
            return True

    foo = mk(Foo())

    if foo:
        assert_type(foo, Foo)
    else:
        assert_type(foo, rz.Err[Exception])


def assert_match_cases() -> None:
    result = mk(1)
    match result:
        case rz.Err(error):
            assert_type(error, E)
        case value:
            assert_type(value, int)


def assert_checked_called_typing_trick() -> None:
    def to_error(e: Exception) -> str | None:
        return str(e)

    def div(x: int, y: int) -> float:
        return x / y

    assert_type(rz.call_checked(ZeroDivisionError, div, 1, 2), Result[float, ZeroDivisionError])  # fmt: skip
    assert_type(rz.call_checked(to_error, div, 1, 0), Result[float, str])
    assert_type(rz.call_checked((ZeroDivisionError, ValueError), div, 1, 0),Result[float, ZeroDivisionError | ValueError])  # fmt: skip
