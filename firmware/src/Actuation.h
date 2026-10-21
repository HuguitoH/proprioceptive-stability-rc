#ifndef ACTUATION_H
#define ACTUATION_H

//  Actuation module: controls the car's physical outputs
//  (steering servo and drive motor via the ESC).
//  This is the "hands" of the car — it acts on the world.

// Initializes the servo and ESC. Call once in setup().
void actuationInit();

// Sets the steering angle. The value is clamped to the
// car's safe range internally.
void setSteering(int angle);

// Sets the motor signal (ESC). 90 = neutral/stopped.
void setMotor(int signal);

#endif
