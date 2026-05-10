import { Entity, PrimaryGeneratedColumn, Column } from "typeorm";

@Entity()
export class User {
  @PrimaryGeneratedColumn() id!: number;
}

@Entity()
export class Order {
  @PrimaryGeneratedColumn() id!: number;
}

@Entity()
export class LineItem {
  @PrimaryGeneratedColumn() id!: number;
}
