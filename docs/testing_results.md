# Testing Results

| Test Case | Input Condition | Expected Output | Actual Output | Status |
|---|---|---|---|---|
| Normal State | Obstacle far away | Robot moves normally | Robot moved normally | Passed |
| Warning State | Obstacle in warning range | Robot slows down | Robot slowed down | Passed |
| Emergency State | Obstacle very close | Robot stops | Robot stopped | Passed |
| CAN Communication | STM32 sends CAN frame | Firebird receives command | Command received | Passed |
| LCD Display | State changes | LCD shows state | State displayed | Passed |
