import assert from 'node:assert/strict';
import { formatApiErrorDetail } from './api';

assert.equal(formatApiErrorDetail('Invalid credentials', 'Bad Request'), 'Invalid credentials');

assert.equal(
  formatApiErrorDetail(
    [
      { loc: ['body', 'password'], msg: 'Field required', type: 'missing' },
      { loc: ['body', 'username'], msg: 'String should have at least 1 character', type: 'string_too_short' },
    ],
    'Unprocessable Entity',
  ),
  'password: Field required; username: String should have at least 1 character',
);

assert.equal(formatApiErrorDetail(undefined, 'Internal Server Error'), 'Internal Server Error');
