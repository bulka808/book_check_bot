from pyrogram import filters, types
from pyrogram.client import Client
from pyrogram.enums import ChatType, MessageEntityType, ParseMode
import dotenv
import os
import json
import asyncio
from typing import Any
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import Mapped
from sqlalchemy import Integer, String
from sqlalchemy.orm import mapped_column
from sqlalchemy import inspect
from sqlalchemy import create_engine


dotenv.load_dotenv()

bot = Client(
    name=os.getenv("LOGIN"),  # type: ignore
    api_id=os.getenv("API_ID"),  # type: ignore
    api_hash=os.getenv("API_HASH"),  # type: ignore
    phone_number=os.getenv("PHONE"),  # type: ignore
)
# ids
NEW = []


class Base(DeclarativeBase):
    def to_dict(self) -> dict[str, Any]:
        return {c.key: getattr(self, c.key) for c in inspect(self).mapper.column_attrs}

    def __repr__(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    series: Mapped[str] = mapped_column(String(100), nullable=False)
    chapter: Mapped[str] = mapped_column(String(100), nullable=False)


class BookCmd(Base):
    __tablename__ = "bookCmds"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(nullable=False)
    chat_title: Mapped[str] = mapped_column(String(100), nullable=True)
    cmd: Mapped[str] = mapped_column(String(100), nullable=None)


engine = create_engine("sqlite:///Books.db", echo=False)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)


# TODO сделать справку


# недо фильтр который сует книжку внутрь сообщения
# TODO сделать нормальную филтрацию, поддержку книг которые пока недоступны
def book_filter(_, message: types.Message):
    if (
        message.caption is None
        or ("По:" not in message.caption and "Автор:" not in message.caption)
        or message.document is None
    ):
        return False

    lines = (message.caption or message.text).splitlines()
    data = {"title": "---", "author": "---", "series": "---", "chapter": "---"}
    data["title"] = lines[0]
    for l in lines:
        if "Автор:" in l:
            data["author"] = l[7:]
        elif "Серия:" in l:
            data["series"] = l[7:]
        elif "По:" in l:
            data["chapter"] = l[4::]

    book = Book(
        title=data["title"],
        author=data["author"],
        series=data["series"],
        chapter=data["chapter"],
    )

    message.book = book

    return True


async def delete_messages_from_list(client: Client, message_list: list[types.Message]):
    messages_in_chats: dict[int, list[int]] = {}
    for message in message_list:
        if message.chat.id not in messages_in_chats:
            messages_in_chats[message.chat.id] = []
            messages_in_chats[message.chat.id].append(message.id)
        else:
            messages_in_chats[message.chat.id].append(message.id)
    for id, messages in messages_in_chats.items():
        await client.delete_messages(chat_id=id, message_ids=messages)


@bot.on_message(filters=filters.command(commands=["add"], prefixes="!"))
async def add(client: Client, message: types.Message):
    session = SessionLocal()
    if (
        message.reply_to_message is not None
        and message.reply_to_message.text is not None
        and message.reply_to_message.entities is not None
    ):
        for entity in message.reply_to_message.entities:
            if entity.type == MessageEntityType.BOT_COMMAND:
                txt = message.reply_to_message.text
                chat_id = message.reply_to_message.chat.id
                chat_title = message.reply_to_message.chat.title

                print(txt)

                bookcmd = BookCmd(chat_id=chat_id, chat_title=chat_title, cmd=txt)
                
                session.add(bookcmd)
                session.commit()
                await message.react(emoji="👍")
    session.close()


@bot.on_message(filters=filters.command(commands=["list"], prefixes="!"))
async def commands_list(client: Client, message: types.Message):
    session = SessionLocal()

    commands = session.query(BookCmd).all()
    session.close()

    if not commands:
        await message.reply(text="Пусто..?")
        return

    txt = "".join(
        f"(ID: {command.id})chat:{command.chat_title:^15.15} | {command.cmd}\n"
        for command in commands
    )

    await message.reply(text=txt)


@bot.on_message(filters=filters.command(commands=["del_command"], prefixes="!"))
async def deleteCommand(client: Client, message: types.Message):
    if len(message.command) < 2:
        await message.reply(text="Неверное число аргументов")
        return

    arg = message.command[1]

    session = SessionLocal()

    session.query(BookCmd).filter(BookCmd.id == arg).delete()
    session.commit()
    session.close()

    await message.react(emoji="👍")


@bot.on_message(filters=filters.command(commands=["del_book"], prefixes="!"))
async def deleteBook(client: Client, message: types.Message):
    if len(message.command) < 2:
        await message.reply(text="Неверное число аргументов")
        return

    arg = message.command[1]

    session = SessionLocal()

    session.query(Book).filter(Book.id == arg).delete()
    session.commit()
    session.close()

    await message.react(emoji="👍")


# просто вывод
@bot.on_message(filters=filters.command(commands=["show"], prefixes="!"))
async def showBooks(client: Client, message: types.Message):
    session = SessionLocal()

    books = session.query(Book).all()
    session.close()

    if not books:
        info = "пусто("
    else:
        info = "".join(
            f"(ID:{book.id})\n__**Название:**__ {book.title}\n__**Автор:**__ {book.author}\
            \n__**Серия:**__ {book.series}\n__**Глава:**__ {book.chapter}\n\n"
            for book in books
        )
    await client.send_message(
        text=info, chat_id=message.from_user.id, parse_mode=ParseMode.MARKDOWN
    )


# проверка и вывод
@bot.on_message(filters=filters.command(commands=["check"], prefixes="!"))
async def check(client: Client, message: types.Message):
    session = SessionLocal()
    commands = session.query(BookCmd).all()
    session.close()

    messages = []
    for command in commands:
        msg = await client.send_message(text=str(command.cmd), chat_id=command.chat_id)
        messages.append(msg)
    await delete_messages_from_list(client, messages)

    await asyncio.sleep(2)

    session = SessionLocal()
    books = session.query(Book).all()
    session.close()

    if not books:
        info = "пусто("
    else:
        session = SessionLocal()
        new = "__**Новое:**__\n" + "".join(
            f"(ID:{book.id})\n__**Навзвание:**__ {book.title}\n__**Автор:**__ {book.author}\
            \n__**Серия:**__ {book.series}\n__**Глава:**__ {book.chapter}\n"
            for new_id in NEW
            for book in session.query(Book).filter_by(id=new_id)
        )
        session.close

        info = "".join(
            f"(ID:{book.id})\n__**Название:**__ {book.title}\n__**Автор:**__ {book.author}\
            \n__**Серия:**__ {book.series}\n__**Глава:**__ {book.chapter}\n\n"
            for book in books
        )

        msg_txt = new + "\n" + info if len(NEW) > 0 else info

        NEW.clear()

    await client.send_message(
        text=msg_txt, chat_id=message.from_user.id, parse_mode=ParseMode.MARKDOWN
    )


@bot.on_message(filters=book_filter)
async def get_books_data(client: Client, message: types.Message):
    book: Book = message.book

    session = SessionLocal()
    existing = (
        session.query(Book)
        .filter_by(series=book.series, author=book.author, title=book.title)
        .first()
    )
    # проверяем есть ли книга в бд, если нет то добавляем, а если есть проверяем главу
    # если вышла новая то обновляем и добавляем id в список
    if existing is None:
        session.add(book)
        session.commit()
        print("New:", book)
    elif existing.chapter != book.chapter:
        existing.chapter = book.chapter
        session.commit()
        print("Updated:", existing)
        NEW.append(existing.id)

    session.close()


bot.run()
