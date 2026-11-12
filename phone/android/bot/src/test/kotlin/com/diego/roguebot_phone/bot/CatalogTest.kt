package com.diego.roguebot_phone.bot

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class CatalogTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test
    fun currentOfferUsesItsOwnRarityWithoutChangingReviewedTags() {
        val catalog = Catalog(File(temporary.root, "skills.json"))
        val original = catalog.lookup("Fire Wave", "Fire damage.", "common", "en")
        catalog.skills["firewave"] = original.copy(auto = false, damageType = "shuriken")
        val upgraded = catalog.lookup("Fire Wave", "Increased fire damage.", "mythic", "en")
        assertEquals("mythic", upgraded.rarity)
        assertEquals("shuriken", upgraded.damageType)
        assertEquals("common", catalog.skills.getValue("firewave").rarity)
    }

    @Test
    fun similarNamesDoNotMergeDifferentElements() {
        val catalog = Catalog(null)
        catalog.lookup("Fire Mastery", "Fire damage.", "common", "en")
        val ice = catalog.lookup("Ice Mastery", "Ice damage.", "legendary", "en")
        assertEquals("ice", ice.damageType)
        assertEquals(2, catalog.skills.size)
    }

    @Test
    fun interruptedWriteKeepsThePreviousFileAndCleansTemporaryData() {
        val destination = temporary.newFolder("destination")
        val previous = File(destination, "keep.json").apply { writeText("reviewed data") }
        assertThrows(java.io.IOException::class.java) { destination.writeAtomically("new data") }
        assertEquals("reviewed data", previous.readText())
        assertEquals(listOf(destination), temporary.root.listFiles()!!.toList())
    }

}
