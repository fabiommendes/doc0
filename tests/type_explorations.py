from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Final,
    Iterable,
    Literal,
    Never,
    TypeIs,
    assert_type,
    cast,
)

MYPY: Final = True
PYRIGHT: Literal[False] = False
EXPECTED: Literal[False] = False


@dataclass
class ErrW[E]:
    e: E


Err = Exception
type Ty[T] = T | list[T]  # analyse problems with T as a member of union
type Fail[T] = T | Err  # Result type, but Error is not parametric
type Result[T, E] = T | ErrW[E]  # Regular result type


def explore_unions_typecheck() -> None:
    """
    Explore mypy and pyright's behaviour in some edge cases with unions.
    """

    def ty[T](x: T) -> Ty[T]:
        return x

    def lst[T](x: Iterable[T]) -> Ty[T]:
        return list(x)

    assert_type(lst([1, 2, 3]), Ty[int])

    def id[T](x: Ty[T]) -> Ty[T]:
        return [y for y in x] if isinstance(x, list) else x

    assert_type(id(1), Ty[int])
    assert_type(id(ty(1)), Ty[int])
    assert_type(id(lst([1, 2, 3])), Ty[int])
    assert_type(id([1, 2, 3]), Ty[int])

    def is_list[T](x: Ty[T]) -> TypeIs[list[T]]:
        return isinstance(x, list)

    def f2[T1, T2](x: Ty[T1], y: Ty[T2]) -> Ty[T1 | T2]:
        if is_list(x) and is_list(y):
            return x + y
        elif is_list(x) and not is_list(y):
            return [*x, y]
        elif is_list(y) and not is_list(x):
            return [x, *y]
        elif not is_list(x) and not is_list(y):
            return [x, y]
        raise ValueError("unreachable")

    assert_type(f2(1, 2), Ty[int])
    assert_type(f2(1, [1, 2]), Ty[int])
    assert_type(f2(1, lst([1, 2])), Ty[int])


def other() -> None:
    @dataclass
    class Box[T]:
        value: T

    def g[T](x: T | Box[T]) -> Box[T] | T:
        if isinstance(x, Box):
            return Box(x.value)
        else:
            return x

    assert_type(g(1), "Box[int] | int")
    assert_type(g(Box(1)), "Box[int] | int")
    assert_type(g(Box([])), "Box[list[Never]] | list[Never]")


def explore_mypy_simple_union_inference() -> None:
    # Result[T] = T | Error

    def unwrap[T](x: T | Exception, /) -> T:
        if isinstance(x, Exception):
            raise x
        else:
            return x

    def is_err(x: Any | Exception, /) -> TypeIs[Exception]:
        return isinstance(x, Exception)

    def id[T](x: T | Exception, /) -> T | Exception:
        return x

    def map[T, R](fn: Callable[[T], R], x: T | Exception, /) -> R | Exception:
        return fn(x) if not is_err(x) else x

    def mk[T](x: T, /) -> T | Exception:
        return x

    def coallesce[T1, T2](
        x: T1 | Exception, y: T2 | Exception, /
    ) -> T1 | T2 | Exception:
        return x if not is_err(x) else y

    x = mk(1)
    y = mk(2)
    f = mk(1.0)
    s = mk("foo")
    e: int | Exception = ValueError()

    assert_type(mk(1), int | Exception)
    assert_type(e, int | Exception)  # pyright: ignore[reportAssertTypeFailure]
    assert_type(map(abs, x), int | Exception)
    assert_type(map(abs, 1), int | Exception)
    assert_type(map(abs, e), int | Exception)  # pyright: ignore[reportAssertTypeFailure]
    assert_type(map(abs, cast("int | Exception", e)), int | Exception)  # type: ignore[redundant-cast]
    assert_type(map(abs, ValueError()), Exception)  # pyright: ignore[reportAssertTypeFailure]
    assert_type(id(x), int | Exception)
    assert_type(id(1), int | Exception)
    assert_type(id(ValueError()), Exception)  # pyright: ignore[reportAssertTypeFailure]
    assert_type(coallesce(x, y), int | Exception)
    assert_type(coallesce(x, f), int | float | Exception)
    assert_type(coallesce(x, s), int | str | Exception)
    assert_type(coallesce(1, 2), int | Exception)


def explore_mypy_wrapper_union_inference() -> None:
    # Result[T, E] = T | Box[E]

    def unwrap[T, E](x: T | ErrW[E], /) -> T:
        if isinstance(x, ErrW):
            raise ValueError(x.e)
        else:
            return x

    def is_err(x: Any, /) -> TypeIs[ErrW[Any]]:
        return isinstance(x, ErrW)

    def id[T, E](x: T | ErrW[E], /) -> T | ErrW[E]:
        return x

    def map[T, E, R](fn: Callable[[T], R], x: T | ErrW[E], /) -> R | ErrW[E]:
        return fn(x) if not is_err(x) else x

    def mk[T](x: T, /) -> T | ErrW[Any]:
        return x

    def coallesce[T1, T2, E](x: T1 | ErrW[E], y: T2 | ErrW[E], /) -> T1 | T2 | ErrW[E]:
        return x if not is_err(x) else y

    def incr(x: int) -> int:
        return x + 1

    x = mk(1)
    y = mk(2)
    f = mk(1.0)
    s = mk("foo")
    e: int | ErrW[str] = ErrW("error")

    assert_type(mk(1), int | ErrW[Any])
    assert_type(e, int | ErrW[str])  # pyright: ignore[reportAssertTypeFailure]
    assert_type(map(abs, x), int | ErrW[Any])
    assert_type(map(abs, 1), int | ErrW[Never])  # pyright: ignore[reportAssertTypeFailure]
    assert_type(map(abs, e), int | ErrW[str])  # pyright: ignore[reportAssertTypeFailure]
    assert_type(map(incr, ErrW("...")), int | ErrW[str])
    assert_type(id(x), int | ErrW[Any])
    assert_type(id(1), int | ErrW[Any])
    assert_type(id(ValueError()), ErrW[Any])  # pyright: ignore[reportAssertTypeFailure]
    assert_type(coallesce(x, y), int | ErrW[Any])
    assert_type(coallesce(x, f), int | float | ErrW[Any])
    assert_type(coallesce(x, s), int | str | ErrW[Any])
    assert_type(coallesce(1, 2), int | ErrW[Any])
