#ifndef PERCEPTION_H
#define PERCEPTION_H

#include "CarState.h"

//  Perception module: reads the sensors and builds the car's
//  self-knowledge (orientation from the IMU, speed from the
//  Hall sensor). This is the car's "proprioception".

// Initializes the IMU and the Hall sensor. Call once in setup().
// Returns true if the IMU was found, false otherwise.
bool perceptionInit();

// Reads the sensors and updates the given CarState with the
// latest orientation and speed. Call every loop iteration.
void updatePerception(CarState& state);

#endif
