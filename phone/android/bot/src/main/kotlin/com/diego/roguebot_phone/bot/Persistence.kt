package com.diego.roguebot_phone.bot

import java.io.File
import java.io.FileOutputStream
import java.nio.file.Files
import java.nio.file.StandardCopyOption

/** Replace a complete file from the same directory; failures leave the previous data intact. */
fun File.writeAtomically(content: String) {
    val destination = absoluteFile
    val directory = destination.parentFile!!
    directory.mkdirs()
    val temporary = File.createTempFile(".${destination.name}.", ".tmp", directory)
    try {
        FileOutputStream(temporary).use { output ->
            output.write(content.toByteArray(Charsets.UTF_8))
            output.fd.sync()
        }
        Files.move(temporary.toPath(), destination.toPath(),
            StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
    } finally {
        temporary.delete()
    }
}
