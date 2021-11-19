"""
The MIT License (MIT)

Copyright (c) 2021-present Texus
Copyright (c) 2021 Pycord

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

import asyncio
import types
from discord.types.channel import VoiceChannel, TextChannel
import functools
import inspect
from collections import OrderedDict
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Union
)

from ..enums import SlashCommandOptionType, ChannelType
from ..member import Member
from ..user import User
from ..message import Message
from .context import ApplicationContext
from ..utils import find, get_or_fetch, async_all

from ..errors import DiscordException, NotFound, ValidationError, ClientException
from .errors import ApplicationCommandError, CheckFailure, ApplicationCommandInvokeError

def wrap_callback(coro):
    @functools.wraps(coro)
    async def wrapped(*args, **kwargs):
        try:
            ret = await coro(*args, **kwargs)
        except ApplicationCommandError:
            raise
        except asyncio.CancelledError:
            return
        except Exception as exc:
            raise ApplicationCommandInvokeError(exc) from exc
        return ret
    return wrapped

def hooked_wrapped_callback(command, ctx, coro):
    @functools.wraps(coro)
    async def wrapped(arg):
        try:
            ret = await coro(arg)
        except ApplicationCommandError:
            raise
        except asyncio.CancelledError:
            return
        except Exception as exc:
            raise ApplicationCommandInvokeError(exc) from exc
        finally:
            await command.call_after_hooks(ctx)
        return ret
    return wrapped

class _BaseCommand:
    __slots__ = ()

class ApplicationCommand(_BaseCommand):
    """The base for application commands
    Added in texus v2.1.0
    """
    cog = None

    def __repr__(self):
        return f"<discord.application.{self.__class__.__name__} name={self.name}>"

    def __eq__(self, other):
        return isinstance(other, self.__class__)

    async def __call__(self, ctx, *args, **kwargs):
        """|coro|
        Calls the command's callback.
        This method bypasses all checks that a command has and does not
        convert the arguments beforehand, so take care to pass the correct
        arguments in.
        """
        return await self.callback(ctx, *args, **kwargs)

    async def prepare(self, ctx: ApplicationContext) -> None:
        # This should be same across all 3 types
        ctx.command = self

        if not await self.can_run(ctx):
            raise CheckFailure(f'The check functions for the command {self.name} failed')

        # TODO: Add cooldown

        await self.call_before_hooks(ctx)

    async def invoke(self, ctx: ApplicationContext) -> None:
        await self.prepare(ctx)

        injected = hooked_wrapped_callback(self, ctx, self._invoke)
        await injected(ctx)

    async def can_run(self, ctx: ApplicationContext) -> bool:

        if not await ctx.bot.can_run(ctx):
            raise CheckFailure(f'The global check functions for command {self.name} failed.')

        predicates = self.checks
        if not predicates:
            # since we have no checks, then we just return True.
            return True

        return await async_all(predicate(ctx) for predicate in predicates)  # type: ignore

    async def dispatch_error(self, ctx: ApplicationContext, error: Exception) -> None:
        ctx.command_failed = True
        cog = self.cog
        try:
            coro = self.on_error
        except AttributeError:
            pass
        else:
            injected = wrap_callback(coro)
            if cog is not None:
                await injected(cog, ctx, error)
            else:
                await injected(ctx, error)

        try:
            if cog is not None:
                local = cog.__class__._get_overridden_method(cog.cog_command_error)
                if local is not None:
                    wrapped = wrap_callback(local)
                    await wrapped(ctx, error)
        finally:
            ctx.bot.dispatch('application_command_error', ctx, error)

    def _get_signature_parameters(self):
        return OrderedDict(inspect.signature(self.callback).parameters)

    def error(self, coro):
        """A decorator that registers a coroutine as a local error handler.
        A local error handler is an :func:`.on_command_error` event limited to
        a single command. However, the :func:`.on_command_error` is still
        invoked afterwards as the catch-all.
        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the local error handler.
        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine.
        """

        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('The error handler must be a coroutine.')

        self.on_error = coro
        return coro

    def has_error_handler(self) -> bool:
        """:class:`bool`: Checks whether the command has an error handler registered.
        """
        return hasattr(self, 'on_error')

    def before_invoke(self, coro):
        """A decorator that registers a coroutine as a pre-invoke hook.
        A pre-invoke hook is called directly before the command is
        called. This makes it a useful function to set up database
        connections or any type of set up required.
        This pre-invoke hook takes a sole parameter, a :class:`.Context`.
        See :meth:`.Bot.before_invoke` for more info.
        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the pre-invoke hook.
        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('The pre-invoke hook must be a coroutine.')

        self._before_invoke = coro
        return coro

    def after_invoke(self, coro):
        """A decorator that registers a coroutine as a post-invoke hook.
        A post-invoke hook is called directly after the command is
        called. This makes it a useful function to clean-up database
        connections or any type of clean up required.
        This post-invoke hook takes a sole parameter, a :class:`.Context`.
        See :meth:`.Bot.after_invoke` for more info.
        Parameters
        -----------
        coro: :ref:`coroutine <coroutine>`
            The coroutine to register as the post-invoke hook.
        Raises
        -------
        TypeError
            The coroutine passed is not actually a coroutine.
        """
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('The post-invoke hook must be a coroutine.')

        self._after_invoke = coro
        return coro

    async def call_before_hooks(self, ctx: ApplicationContext) -> None:
        # now that we're done preparing we can call the pre-command hooks
        # first, call the command local hook:
        cog = self.cog
        if self._before_invoke is not None:
            # should be cog if @commands.before_invoke is used
            instance = getattr(self._before_invoke, '__self__', cog)
            # __self__ only exists for methods, not functions
            # however, if @command.before_invoke is used, it will be a function
            if instance:
                await self._before_invoke(instance, ctx)  # type: ignore
            else:
                await self._before_invoke(ctx)  # type: ignore

        # call the cog local hook if applicable:
        if cog is not None:
            hook = cog.__class__._get_overridden_method(cog.cog_before_invoke)
            if hook is not None:
                await hook(ctx)

        # call the bot global hook if necessary
        hook = ctx.bot._before_invoke
        if hook is not None:
            await hook(ctx)

    async def call_after_hooks(self, ctx: ApplicationContext) -> None:
        cog = self.cog
        if self._after_invoke is not None:
            instance = getattr(self._after_invoke, '__self__', cog)
            if instance:
                await self._after_invoke(instance, ctx)  # type: ignore
            else:
                await self._after_invoke(ctx)  # type: ignore

        # call the cog local hook if applicable:
        if cog is not None:
            hook = cog.__class__._get_overridden_method(cog.cog_after_invoke)
            if hook is not None:
                await hook(ctx)

        hook = ctx.bot._after_invoke
        if hook is not None:
            await hook(ctx)

    @property
    def full_parent_name(self) -> str:
        """:class:`str`: Retrieves the fully qualified parent command name.
        This the base command name required to execute it. For example,
        in ``/one two three`` the parent name would be ``one two``.
        """
        entries = []
        command = self
        while command.parent is not None and hasattr(command.parent, "name"):
            command = command.parent
            entries.append(command.name)

        return ' '.join(reversed(entries))

    def qualified_name(self) -> str:
        """:class:`str`: Retrieves the fully qualified command name.
        This is the full parent name with the command name as well.
        For example, in ``/one two three`` the qualified name would be
        ``one two three``.
        """

        parent = self.full_parent_name

        if parent:
            return parent + ' ' + self.name
        else:
            return self.name


class SlashCommand(ApplicationCommand):
    r"""Implements The usage of slash commands
    Also subclasses ApplicationCommand.
    Added In v2.1.0
    -----------
    name: :class:`str`
        The name of the command.
    callback: :ref:`coroutine <coroutine>`
        The coroutine that is executed when the command is called.
    description: Optional[:class:`str`]
        The description for the command.
    guild_ids: Optional[List[:class:`int`]]
        The ids of the guilds where this command will be registered.
    options: List[:class:`Option`]
        The parameters for this command.
    parent: Optional[:class:`SlashCommandGroup`]
        The parent group that this command belongs to. ``None`` if there
        isn't one.
    default_permission: :class:`bool`
        Whether the command is enabled by default when it is added to a guild.
    permissions: List[:class:`Permission`]
        The permissions for this command.
        .. note::
            If this is not empty then default_permissions will be set to False.
    cog: Optional[:class:`Cog`]
        The cog that this command belongs to. ``None`` if there isn't one.
    checks: List[Callable[[:class:`.ApplicationContext`], :class:`bool`]]
        A list of predicates that verifies if the command could be executed
        with the given :class:`.ApplicationContext` as the sole parameter. If an exception
        is necessary to be thrown to signal failure, then one inherited from
        :exc:`.CommandError` should be used. Note that if the checks fail then
        :exc:`.CheckFailure` exception is raised to the :func:`.on_application_command_error`
        event.
    """
    type = 1

    def __new__(cls, *args, **kwargs) -> SlashCommand:
        self = super().__new__(cls)

        self.__original_kwargs__ = kwargs.copy()
        return self

    def __init__(self, func: Callable, *args, **kwargs) -> None:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Callback must be a coroutine.")
        self.callback = func

        self.guild_ids: Optional[List[int]] = kwargs.get("guild_ids", None)

        name = kwargs.get("name") or func.__name__
        validate_chat_input_name(name)
        self.name: str = name
        self.id = None

        description = kwargs.get("description") or (
            inspect.cleandoc(func.__doc__).splitlines()[0]
            if func.__doc__ is not None
            else "No description provided"
        )
        validate_chat_input_description(description)
        self.description: str = description
        self.parent = kwargs.get('parent')
        self.is_subcommand: bool = self.parent is not None

        self.cog = None

        params = self._get_signature_parameters()
        self.options: List[Option] = kwargs.get('options') or self._parse_options(params)

        try:
            checks = func.__commands_checks__
            checks.reverse()
        except AttributeError:
            checks = kwargs.get('checks', [])

        self.checks = checks

        self._before_invoke = None
        self._after_invoke = None

        # Permissions
        self.default_permission = kwargs.get("default_permission", True)
        self.permissions: List[Permission] = getattr(func, "__app_cmd_perms__", []) + kwargs.get("permissions", [])
        if self.permissions and self.default_permission:
            self.default_permission = False

    def _parse_options(self, params) -> List[Option]:
        final_options = []

        if list(params.items())[0][0] == "self":
            temp = list(params.items())
            temp.pop(0)
            params = dict(temp)
        params = iter(params.items())

        # next we have the 'ctx' as the next parameter
        try:
            next(params)
        except StopIteration:
            raise ClientException(
                f'Callback for {self.name} command is missing "ctx" parameter.'
            )

        final_options = []

        for p_name, p_obj in params:

            option = p_obj.annotation
            if option == inspect.Parameter.empty:
                option = str

            if self._is_typing_union(option):
                if self._is_typing_optional(option):
                    option = Option(
                        option.__args__[0], "No description provided", required=False
                    )
                else:
                    option = Option(
                        option.__args__, "No description provided"
                    )

            if not isinstance(option, Option):
                option = Option(option, "No description provided")
                if p_obj.default != inspect.Parameter.empty:
                    option.required = False

            option.default = option.default if option.default is not None else p_obj.default

            if option.default == inspect.Parameter.empty:
                option.default = None

            if option.name is None:
                option.name = p_name
            option._parameter_name = p_name

            final_options.append(option)

        return final_options

    def _is_typing_union(self, annotation):
        return (
                getattr(annotation, '__origin__', None) is Union
                or type(annotation) is getattr(types, "UnionType", Union)
        )  # type: ignore

    def _is_typing_optional(self, annotation):
        return self._is_typing_union(annotation) and type(None) in annotation.__args__  # type: ignore

    def to_dict(self) -> Dict:
        as_dict = {
            "name": self.name,
            "description": self.description,
            "options": [o.to_dict() for o in self.options],
            "default_permission": self.default_permission,
        }
        if self.is_subcommand:
            as_dict["type"] = SlashCommandOptionType.sub_command.value

        return as_dict

    def __eq__(self, other) -> bool:
        return (
                isinstance(other, SlashCommand)
                and other.name == self.name
                and other.description == self.description
        )

    async def _invoke(self, ctx: ApplicationContext) -> None:
        # TODO: Parse the args better
        kwargs = {}
        for arg in ctx.interaction.data.get("options", []):
            op = find(lambda x: x.name == arg["name"], self.options)
            arg = arg["value"]

            # Checks if input_type is user, role or channel
            if (
                    SlashCommandOptionType.user.value
                    <= op.input_type.value
                    <= SlashCommandOptionType.role.value
            ):
                name = "member" if op.input_type.name == "user" else op.input_type.name
                arg = await get_or_fetch(ctx.guild, name, int(arg), default=int(arg))

            elif op.input_type == SlashCommandOptionType.mentionable:
                arg_id = int(arg)
                arg = await get_or_fetch(ctx.guild, "member", arg_id)
                if arg is None:
                    arg = ctx.guild.get_role(arg_id) or arg_id

            elif op.input_type == SlashCommandOptionType.string and op._converter is not None:
                arg = await op._converter.convert(ctx, arg)

            kwargs[op._parameter_name] = arg

        for o in self.options:
            if o._parameter_name not in kwargs:
                kwargs[o._parameter_name] = o.default

        if self.cog is not None:
            await self.callback(self.cog, ctx, **kwargs)
        else:
            await self.callback(ctx, **kwargs)

    async def invoke_autocomplete_callback(self, ctx: AutocompleteContext):
        values = {i.name: i.default for i in self.options}

        for op in ctx.interaction.data.get("options", []):
            if op.get("focused", False):
                option = find(lambda o: o.name == op["name"], self.options)
                values.update({
                    i["name"]: i["value"]
                    for i in ctx.interaction.data["options"]
                })
                ctx.command = self
                ctx.focused = option
                ctx.value = op.get("value")
                ctx.options = values

                if len(inspect.signature(option.autocomplete).parameters) == 2:
                    instance = getattr(option.autocomplete, "__self__", ctx.cog)
                    result = option.autocomplete(instance, ctx)
                else:
                    result = option.autocomplete(ctx)

                if asyncio.iscoroutinefunction(option.autocomplete):
                    result = await result

                choices = [
                              o if isinstance(o, OptionChoice) else OptionChoice(o)
                              for o in result
                          ][:25]
                return await ctx.interaction.response.send_autocomplete_result(choices=choices)

    def copy(self):
        """Makes A Copy Of The Command
        Returns
        --------
        :class:`SlashCommand`
            A new instance of this command.
        """
        ret = self.__class__(self.callback, **self.__original_kwargs__)
        return self._ensure_assignment_on_copy(ret)

    def _ensure_assignment_on_copy(self, other):
        other._before_invoke = self._before_invoke
        other._after_invoke = self._after_invoke
        if self.checks != other.checks:
            other.checks = self.checks.copy()
        # if self._buckets.valid and not other._buckets.valid:
        #    other._buckets = self._buckets.copy()
        # if self._max_concurrency != other._max_concurrency:
        #    # _max_concurrency won't be None at this point
        #    other._max_concurrency = self._max_concurrency.copy()  # type: ignore

        try:
            other.on_error = self.on_error
        except AttributeError:
            pass
        return other

    def _update_copy(self, kwargs: Dict[str, Any]):
        if kwargs:
            kw = kwargs.copy()
            kw.update(self.__original_kwargs__)
            copy = self.__class__(self.callback, **kw)
            return self._ensure_assignment_on_copy(copy)
        else:
            return self.copy()


channel_type_map = {
    'TextChannel': ChannelType.text,
    'VoiceChannel': ChannelType.voice,
    'StageChannel': ChannelType.stage_voice,
    'CategoryChannel': ChannelType.category
}
