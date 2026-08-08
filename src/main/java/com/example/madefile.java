package com.example;
public class madefile{
public static void main(String[] args){
    SystemAssess sys = new SystemAssess();
    double tokenestimate = sys.estimate(1.5, 4.83);
    System.out.println(tokenestimate);
}
}
