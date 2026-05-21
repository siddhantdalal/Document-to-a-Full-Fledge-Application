# Todo App

A simple todo list application.

## Users

Users can sign up with an email and password and log in to manage their own todos.

## Features

- Create a todo with a title and an optional description.
- List all of the user's todos.
- Mark a todo as completed.
- Delete a todo.

## Screens

- **Login** at `/login` — email/password form and a link to `/signup`.
- **Signup** at `/signup` — email/password form.
- **Todos** at `/` — list of the user's todos with an input to add a new one.

## API

- `POST /signup` — create a user
- `POST /login` — authenticate, returns a JWT
- `GET /todos` — list todos for the current user
- `POST /todos` — create a todo
- `PATCH /todos/{id}` — update (typically to mark complete)
- `DELETE /todos/{id}` — delete
