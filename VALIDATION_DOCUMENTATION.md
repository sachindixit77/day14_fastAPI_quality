# Validation Documentation

## Day 14 - Employee Management API

This document describes the validation rules implemented in the Employee Management API.

---

## 1. Employee Name Validation

The employee name is required.

Rules:

- Minimum length: 2 characters
- Maximum length: 100 characters
- Empty or whitespace-only names are not allowed

### Valid Example

```json
{
  "name": "Rahul Sharma"
}