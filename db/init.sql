-- ============================================================
-- Seed data for Nimbus Technologies (a FICTIONAL company).
-- Runs automatically when the Postgres container starts for the first time.
-- ============================================================

CREATE TABLE IF NOT EXISTS employees (
    id          VARCHAR(10)  PRIMARY KEY,      -- e.g. 'E101'
    name        VARCHAR(100) NOT NULL,
    department  VARCHAR(50)  NOT NULL,
    manager     VARCHAR(100),                  -- manager's name (NULL for the CEO)
    email       VARCHAR(100) NOT NULL,
    phone       VARCHAR(20)  NOT NULL
);

CREATE TABLE IF NOT EXISTS leave_balances (
    employee_id VARCHAR(10) NOT NULL REFERENCES employees(id),
    leave_type  VARCHAR(20) NOT NULL,          -- 'annual', 'sick', 'casual'
    total       INT NOT NULL,
    used        INT NOT NULL,
    remaining   INT NOT NULL,
    PRIMARY KEY (employee_id, leave_type)
);

INSERT INTO employees (id, name, department, manager, email, phone) VALUES
  ('E101', 'Aarav Sharma',   'Engineering', 'Neha Kapoor',  'aarav.sharma@nimbustech.example',   '+91-98100-11001'),
  ('E102', 'Priya Verma',    'HR',          'Rohit Mehta',  'priya.verma@nimbustech.example',    '+91-98100-11002'),
  ('E103', 'Kabir Singh',    'Finance',     'Anita Desai',  'kabir.singh@nimbustech.example',    '+91-98100-11003'),
  ('E104', 'Sneha Iyer',     'Engineering', 'Neha Kapoor',  'sneha.iyer@nimbustech.example',     '+91-98100-11004'),
  ('E105', 'Rahul Gupta',    'IT Support',  'Vikram Rao',   'rahul.gupta@nimbustech.example',    '+91-98100-11005'),
  ('E106', 'Meera Nair',     'Marketing',   'Sanjay Joshi', 'meera.nair@nimbustech.example',     '+91-98100-11006'),
  ('E107', 'Arjun Reddy',    'Sales',       'Sanjay Joshi', 'arjun.reddy@nimbustech.example',    '+91-98100-11007'),
  ('E108', 'Ananya Bose',    'Engineering', 'Neha Kapoor',  'ananya.bose@nimbustech.example',    '+91-98100-11008'),
  ('E109', 'Vivek Malhotra', 'IT Support',  'Vikram Rao',   'vivek.malhotra@nimbustech.example', '+91-98100-11009'),
  ('E110', 'Ishita Chawla',  'HR',          'Rohit Mehta',  'ishita.chawla@nimbustech.example',  '+91-98100-11010');

-- remaining = total - used (kept as a stored column so it is easy to read)
INSERT INTO leave_balances (employee_id, leave_type, total, used, remaining) VALUES
  ('E101', 'annual', 18,  6, 12), ('E101', 'sick', 10, 2,  8), ('E101', 'casual', 6, 1, 5),
  ('E102', 'annual', 18, 11,  7), ('E102', 'sick', 10, 3,  7), ('E102', 'casual', 6, 4, 2),
  ('E103', 'annual', 18,  3, 15), ('E103', 'sick', 10, 0, 10), ('E103', 'casual', 6, 2, 4),
  ('E104', 'annual', 18, 14,  4), ('E104', 'sick', 10, 5,  5), ('E104', 'casual', 6, 6, 0),
  ('E105', 'annual', 18,  8, 10), ('E105', 'sick', 10, 1,  9), ('E105', 'casual', 6, 3, 3),
  ('E106', 'annual', 18,  0, 18), ('E106', 'sick', 10, 0, 10), ('E106', 'casual', 6, 0, 6),
  ('E107', 'annual', 18,  9,  9), ('E107', 'sick', 10, 4,  6), ('E107', 'casual', 6, 2, 4),
  ('E108', 'annual', 18,  5, 13), ('E108', 'sick', 10, 2,  8), ('E108', 'casual', 6, 1, 5),
  ('E109', 'annual', 18, 16,  2), ('E109', 'sick', 10, 7,  3), ('E109', 'casual', 6, 5, 1),
  ('E110', 'annual', 18,  7, 11), ('E110', 'sick', 10, 1,  9), ('E110', 'casual', 6, 2, 4);
