# Requirements Document

## Introduction

This document defines the requirements for a full-stack secure password manager website. The system allows authenticated users to securely store, view, edit, and delete their saved credentials (website name, email/username, and password). All sensitive data is encrypted exclusively on the backend using the Python `cryptography` library (Fernet/AES). The frontend is built with React and TypeScript; the database is PostgreSQL. All communication occurs over HTTPS.

The system supports two roles — User and Admin — with a profile/permission system managed by the Admin. The UI is responsive and available in English (default) and Spanish. A second phase introduces CAPTCHA on login and email verification with account deactivation enforcement.

---

## Glossary

- **System**: The full-stack password manager web application (backend + frontend).
- **Backend**: The Python server responsible for all encryption, decryption, and database operations.
- **Frontend**: The React + TypeScript web interface presented to the user.
- **Database**: The PostgreSQL relational database that stores all persistent data.
- **Authenticator**: The backend component that validates user credentials and manages session tokens.
- **Encryptor**: The backend component that encrypts and decrypts credential passwords using Fernet/AES.
- **Credential**: A stored record consisting of a website name, email or username, and an encrypted password belonging to a specific user.
- **User**: An authenticated account holder with access to personal credential management screens.
- **Admin**: An authenticated account holder with elevated permissions, including full CRUD access to all screens and profile/permission assignment.
- **Profile**: A named permission set that defines which application screens a User role may access.
- **Audit_Log**: The database table that records every user-initiated data operation (SELECT, INSERT, UPDATE, DELETE).
- **Audit_Columns**: The six metadata columns present on every table: `creation_date`, `creation_time`, `creation_user_id`, `modification_date`, `modification_time`, `modification_user_id`.
- **Session**: An authenticated browser session established after successful login, tracked via a secure token.
- **Password_Confirmation_Prompt**: A modal dialog that requires the user to re-enter their own account password before a sensitive operation is executed.
- **Eye_Toggle**: A UI control that shows or hides a password field.
- **Visibility_Timer**: A per-row countdown of 60 seconds after which a revealed credential password is automatically hidden.
- **CAPTCHA**: A challenge-response test (free, e.g., hCaptcha) embedded on the login page to block automated login attempts.
- **Verification_Email**: A one-time email sent to a new user containing a link that marks the user's email as verified in the Database.
- **Deactivation_Deadline**: The date 30 days after account creation, stored per user, after which an unverified account is deactivated.

---

## Requirements

### Requirement 1: User Registration (Sign-Up)

**User Story:** As a visitor, I want to create an account with a secure password, so that I can access the password manager.

#### Acceptance Criteria

1. THE System SHALL provide a sign-up page accessible from the login page.
2. WHEN a visitor submits the sign-up form, THE System SHALL collect `username`, `email`, and `password`.
3. WHEN a visitor submits the sign-up form, THE System SHALL require a `password_confirmation` field whose value matches the `password` field exactly.
4. IF the `password` and `password_confirmation` values do not match, THEN THE System SHALL display a field-level error message and prevent account creation.
5. WHEN validating the `password` field on sign-up, THE System SHALL enforce a minimum length of 12 characters, at least one uppercase letter, at least one lowercase letter, at least one digit, and at least one symbol from the set `@`, `$`, `!`.
6. IF the `password` does not satisfy the password rules, THEN THE System SHALL display a descriptive error listing each unmet rule and prevent account creation.
7. WHEN a visitor submits a valid sign-up form, THE Backend SHALL hash the user's account password using a secure one-way hashing algorithm (e.g., bcrypt) before storing it in the Database.
8. WHEN a new account is created, THE Backend SHALL set `creation_date`, `creation_time`, and `creation_user_id` on the user record.
9. WHEN a new account is created in Phase 2, THE Backend SHALL record the `Deactivation_Deadline` as 30 days from the account creation date and set the `email_verified` flag to `false`.
10. WHEN a new account is created in Phase 2, THE Backend SHALL send a `Verification_Email` to the registered email address containing a unique verification link.

---

### Requirement 2: User Authentication (Login)

**User Story:** As a registered user, I want to log in securely, so that I can access my saved credentials.

#### Acceptance Criteria

1. THE System SHALL provide a login page as the application entry point.
2. WHEN a user submits valid credentials on the login page, THE Authenticator SHALL establish a Session and redirect the user to the main application.
3. IF a user submits invalid credentials, THEN THE Authenticator SHALL return a generic error message that does not reveal whether the username or password was incorrect.
4. WHEN a session is established, THE Backend SHALL issue a secure, short-lived token (e.g., JWT with HTTPS-only transmission) to the Frontend.
5. WHEN a session token expires, THE System SHALL redirect the user to the login page.
6. WHERE Phase 2 is enabled, THE Login_Page SHALL include a CAPTCHA challenge that the user must pass before credentials are submitted.
7. WHERE Phase 2 is enabled, WHEN a user with an unverified email logs in, THE System SHALL display a modal informing the user that email verification is required, with an option to resend the `Verification_Email`.
8. WHERE Phase 2 is enabled, IF resending the verification email is requested, THEN THE Backend SHALL send a new `Verification_Email` without modifying the existing `Deactivation_Deadline`.
9. WHERE Phase 2 is enabled, WHEN a user whose `Deactivation_Deadline` has passed and whose `email_verified` flag is `false` attempts to log in, THE Authenticator SHALL reject the login and display a message stating the account is deactivated.

---

### Requirement 3: Role and Profile Management

**User Story:** As an Admin, I want to assign profiles and permissions to users, so that I can control which screens each user role can access.

#### Acceptance Criteria

1. THE System SHALL support exactly two roles: `User` and `Admin`.
2. THE System SHALL provide an Admin-only profile assignment page where an Admin can assign a Profile to any User account.
3. WHEN an Admin assigns or modifies a Profile, THE Backend SHALL update the user's permission set and record the change in Audit_Columns.
4. WHILE a user is logged in with the `User` role, THE System SHALL restrict navigation to only the screens permitted by the user's assigned Profile.
5. WHILE a user is logged in with the `Admin` role, THE System SHALL grant access to all application screens and all CRUD operations on all records.
6. IF a User attempts to access a screen not permitted by their Profile, THEN THE System SHALL return a 403 Forbidden response and redirect to the user's permitted home screen.
7. THE System SHALL include an Admin page listing all users with their currently assigned Profile, allowing the Admin to reassign Profiles.

---

### Requirement 4: Save Credentials

**User Story:** As a User, I want to save my credentials for a website, so that I can retrieve them later securely.

#### Acceptance Criteria

1. THE System SHALL provide a "Save Credentials" page accessible to authenticated users with the required Profile permission.
2. THE Save_Credentials_Page SHALL include a mandatory `website_name` field that accepts alphanumeric input.
3. THE Save_Credentials_Page SHALL include a mandatory `email` field by default.
4. WHEN the `Username Login` checkbox is checked on the Save_Credentials_Page, THE System SHALL make the `email` field optional and make a `username` field mandatory instead.
5. THE Save_Credentials_Page SHALL include a mandatory `password` field rendered as hidden (masked) by default with an Eye_Toggle button.
6. WHEN the Eye_Toggle is activated on the Save_Credentials_Page, THE System SHALL display the plaintext value of the `password` field.
7. WHEN the Eye_Toggle is deactivated on the Save_Credentials_Page, THE System SHALL mask the `password` field again.
8. WHEN a user attempts to save a new Credential, THE System SHALL display a Password_Confirmation_Prompt requiring the user to enter their own account password.
9. IF the account password entered in the Password_Confirmation_Prompt is incorrect, THEN THE Backend SHALL reject the save operation and return an error message.
10. WHEN a valid save operation is confirmed, THE Encryptor SHALL encrypt the credential password before THE Backend stores the Credential record in the Database.
11. WHEN a Credential record is saved, THE Backend SHALL record `creation_date`, `creation_time`, and `creation_user_id` in the Audit_Columns of the credential record.
12. WHEN a Credential record is saved, THE Audit_Log SHALL record the INSERT operation with the `user_id`, operation type `INSERT`, and the new credential record's identifier.
13. THE System SHALL validate the `email` field against standard RFC 5321 email format rules and SHALL reject addresses belonging to known disposable/temporary email domains.

---

### Requirement 5: View and Search Credentials

**User Story:** As a User, I want to search my saved credentials and view them securely, so that I can retrieve login information when needed.

#### Acceptance Criteria

1. THE System SHALL provide a "View/Search Credentials" page accessible to authenticated users with the required Profile permission.
2. THE Search_Page SHALL include a search input that filters Credentials by `website_name` or `email` using a case-insensitive partial (contains) match.
3. WHEN a search is executed, THE Backend SHALL return only Credentials belonging to the currently authenticated user.
4. WHEN search results are displayed, THE System SHALL render the results in a table where the `password` column is always masked by default.
5. WHEN the Eye_Toggle icon is clicked for a table row, THE System SHALL display a Password_Confirmation_Prompt requiring the user to enter their own account password.
6. WHEN the account password in the Password_Confirmation_Prompt is verified, THE Encryptor SHALL decrypt the Credential password and THE Frontend SHALL display it in the table row.
7. WHEN a credential password is revealed, THE System SHALL start a Visibility_Timer of 60 seconds for that individual row.
8. WHEN the Visibility_Timer for a row reaches zero, THE System SHALL automatically mask the password in that row.
9. WHEN a user manually clicks the Eye_Toggle on a revealed row, THE System SHALL immediately mask the password and stop the Visibility_Timer for that row.
10. IF a user attempts to reveal a credential password while another credential password is currently visible, THEN THE System SHALL display a warning modal stating that a password is already visible.
11. WHEN the warning modal is displayed, THE System SHALL provide a "Continue" button that hides the currently visible password and then proceeds to the Password_Confirmation_Prompt for the newly requested row.
12. WHEN the warning modal is displayed, THE System SHALL provide a "Cancel" button that closes the modal without revealing any additional passwords.
13. WHEN any Eye_Toggle is clicked, THE System SHALL always display the Password_Confirmation_Prompt regardless of prior interactions in the current session.
14. WHEN the Audit_Log records a credential password retrieval, THE Backend SHALL log the operation as `SELECT` with the `user_id` and the credential record identifier.

---

### Requirement 6: Edit Credentials

**User Story:** As a User, I want to edit my saved credentials, so that I can keep them up to date.

#### Acceptance Criteria

1. THE Search_Page SHALL display an edit icon for each Credential row in the results table.
2. WHEN the edit icon is clicked, THE System SHALL navigate the user to an Edit Credentials page pre-populated with the existing `website_name`, `email` (or `username`), and a masked `password` field.
3. THE Edit_Credentials_Page SHALL allow the user to modify the `website_name`, `email`/`username`, and `password` fields.
4. THE Edit_Credentials_Page SHALL include a "Cancel" button that navigates back to the Search_Page without saving any changes.
5. WHEN the user clicks "Update" on the Edit_Credentials_Page, THE System SHALL display a Password_Confirmation_Prompt.
6. IF the account password entered in the Password_Confirmation_Prompt is incorrect, THEN THE Backend SHALL reject the update operation.
7. WHEN a valid update is confirmed, THE Encryptor SHALL re-encrypt the (possibly changed) credential password and THE Backend SHALL persist the updated record.
8. WHEN a Credential record is updated, THE Backend SHALL record `modification_date`, `modification_time`, and `modification_user_id` in the Audit_Columns.
9. WHEN a Credential record is updated, THE Audit_Log SHALL record the UPDATE operation with the `user_id`, operation type `UPDATE`, and the affected credential record's identifier.

---

### Requirement 7: Delete Credentials

**User Story:** As a User, I want to delete saved credentials I no longer need, so that my vault stays current.

#### Acceptance Criteria

1. THE Search_Page SHALL display a delete icon for each Credential row in the results table.
2. WHEN the delete icon is clicked, THE System SHALL display a confirmation modal asking the user to confirm deletion.
3. THE Confirmation_Modal SHALL include a "Cancel" button that closes the modal without deleting any record.
4. WHEN the user clicks "Delete" in the Confirmation_Modal, THE System SHALL display a Password_Confirmation_Prompt.
5. IF the account password entered in the Password_Confirmation_Prompt is incorrect, THEN THE Backend SHALL reject the delete operation.
6. WHEN a valid deletion is confirmed, THE Backend SHALL permanently remove the Credential record from the Database.
7. WHEN a Credential record is deleted, THE Audit_Log SHALL record the DELETE operation with the `user_id`, operation type `DELETE`, and the affected credential record's identifier.

---

### Requirement 8: Encryption and Data Security

**User Story:** As a system operator, I want all credential passwords encrypted on the backend, so that plaintext passwords are never stored in the database.

#### Acceptance Criteria

1. THE Encryptor SHALL encrypt every credential password using AES-based symmetric encryption (Fernet) before any credential record is persisted to the Database.
2. THE Encryptor SHALL decrypt credential passwords only upon a verified retrieval request from an authenticated user who owns the Credential.
3. THE Backend SHALL never transmit an encryption key or intermediate plaintext credential password to the Frontend.
4. THE System SHALL enforce HTTPS for all client-to-backend communication.
5. THE Backend SHALL store only the hashed form of user account passwords; plaintext account passwords SHALL NOT be persisted.
6. THE Backend SHALL use parameterized queries or an ORM's parameter-binding mechanism for all Database operations to prevent SQL injection.
7. WHEN multiple concurrent users perform operations simultaneously, THE Database SHALL use transactions with appropriate isolation levels to prevent data corruption and cross-user data leakage.

---

### Requirement 9: Database Schema and Auditing

**User Story:** As a database administrator, I want a well-structured schema with audit columns and an audit log, so that I can trace all data changes.

#### Acceptance Criteria

1. THE Database SHALL contain a `users` table with columns for `user_id` (PK), `username`, `email`, `password_hash`, `role`, `email_verified` (boolean), `deactivation_deadline` (date), and Audit_Columns.
2. THE Database SHALL contain a `profiles` table defining available permission sets, with Audit_Columns.
3. THE Database SHALL contain a `user_profiles` table mapping users to profiles, with Audit_Columns.
4. THE Database SHALL contain a `credentials` table with columns for `credential_id` (PK), `user_id` (FK → `users`), `website_name`, `email_or_username`, `is_username_login` (boolean), `encrypted_password`, and Audit_Columns.
5. THE Database SHALL contain an `audit_log` table with columns for `log_id` (PK), `user_id` (FK → `users`), `operation` (SELECT/INSERT/UPDATE/DELETE), `affected_record_id`, `operation_date`, and `operation_time`.
6. THE Database schema SHALL include foreign key constraints between all related tables.
7. THE Database schema SHALL include indexes on `credentials.user_id`, `credentials.website_name`, `credentials.email_or_username`, and `audit_log.user_id` to support efficient queries under concurrent load.
8. EVERY table in the Database SHALL include the six Audit_Columns: `creation_date` (date), `creation_time` (time), `creation_user_id` (integer FK → `users`), `modification_date` (date), `modification_time` (time), `modification_user_id` (integer FK → `users`).
9. THE Database setup script SHALL create a non-superuser application database role granted only the permissions (SELECT, INSERT, UPDATE, DELETE on relevant tables) required for the System to function, without granting superuser or schema-owner privileges.

---

### Requirement 10: Internationalization

**User Story:** As a user, I want to switch the interface language between English and Spanish, so that I can use the application in my preferred language.

#### Acceptance Criteria

1. THE System SHALL render all UI text in English by default.
2. THE Frontend SHALL include a language toggle control in the application header.
3. WHEN the language toggle is set to Spanish, THE Frontend SHALL render all UI labels, messages, and error text in Spanish without reloading the page.
4. WHEN the language toggle is set to English, THE Frontend SHALL render all UI labels, messages, and error text in English without reloading the page.
5. THE System SHALL persist the selected language preference for the duration of the browser session.

---

### Requirement 11: Responsive User Interface

**User Story:** As a user, I want the application to work on any device screen size, so that I can access my passwords from desktop, tablet, or mobile.

#### Acceptance Criteria

1. THE Frontend SHALL implement a responsive layout that adapts to screen widths from 320 px (mobile) through 1920 px (large desktop).
2. THE Frontend SHALL render all interactive controls (buttons, inputs, icons) at touch-friendly sizes on screens narrower than 768 px.
3. THE Frontend SHALL ensure that all tables on the Search_Page remain horizontally scrollable on screens narrower than 768 px so that no data is clipped.

---

### Requirement 12: Documentation

**User Story:** As a developer and end user, I want comprehensive documentation, so that I can understand how to use and maintain the system.

#### Acceptance Criteria

1. THE System repository SHALL include a `requirements.md` file capturing all functional and non-functional requirements.
2. THE System repository SHALL include a `README.md` file that describes all application screens and user workflows in simplified, user-facing language without exposing internal security implementation details.
3. THE System repository SHALL include a `ARCHITECTURE.md` file that explains the technical flow from Database through Backend to Frontend, including the encryption lifecycle, authentication flow, and database schema overview.
