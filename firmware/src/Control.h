#ifndef CONTROL_H
#define CONTROL_H

#include "CarState.h"

//  Control module: the closed-loop stability control (PID).
//  It compares what the car should do with what it actually
//  does (from the sensors) and computes the correction.
//  This is the "reflex" that keeps the car stable.

// Initializes the controller. Call once in setup().
void controlInit();

// Given the current state and the desired yaw rate,
// returns the steering angle that corrects the error.
int computeSteering(const CarState& state, float targetYawRate);

#endif
