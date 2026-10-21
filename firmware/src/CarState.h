#ifndef CAR_STATE_H
#define CAR_STATE_H

//  Groups the car's ORIENTATION in space (from the IMU)
struct Orientation {
  float pitch;      // forward-backward tilt (degrees)
  float roll;       // side-to-side tilt (degrees)
  float yaw;        // horizontal rotation, accumulated (degrees) - drifts
  float yawRate;    // rotation speed (degrees/s) - direct from gyro, no drift
};

//  Groups the car's SPEED (from the Hall sensor)
struct Speed {
  float driveshaftRpm;   // driveshaft revolutions per minute
  float realSpeed;       // car speed (m/s) - computed after calibration
};

//  MAIN structure: everything the car senses about itself.
//  This is the car's "state card".
struct CarState {
  Orientation orientation;   // how it is rotated
  Speed speed;               // how fast it is going
};

#endif
