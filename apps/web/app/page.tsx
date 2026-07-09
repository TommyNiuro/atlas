import { redirect } from "next/navigation";

// ponytail: el prototipo de Claude Design es el frontend base del Bloque 0.
// En el Bloque 4 se descompone en componentes React conectados a la API.
export default function Home() {
  redirect("/prototype.html");
}
